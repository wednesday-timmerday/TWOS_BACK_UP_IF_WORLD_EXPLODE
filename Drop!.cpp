// threedee_renderer.cpp
//
// Linux:   g++ -std=c++17 -shared -fPIC -O2 -o threedee_renderer.so threedee_renderer.cpp -lGL -lX11
// Windows: g++ -std=c++17 -shared -O2 -static -static-libgcc -static-libstdc++
//              -o threedee_renderer.dll threedee_renderer.cpp -lopengl32 -lgdi32
//
// C++ creates a hidden offscreen GL context (NOT on the SDL window).
// It renders into an FBO and exposes raw RGBA pixels via get_frame_rgba().
// Python blits those pixels as a pygame Surface — SDL owns all window flipping.
// This means zero fighting between C++ and SDL.
//
// API:
//   init_renderer(width, height)   -> int   (1=ok)
//   set_viewport(w, h)
//   load_obj(filename, scale, px, py, pz, angle, r, g, b, spin_speed) -> int
//   update(dt, key_w, key_s, key_a, key_d)
//   render_frame(dt)
//   get_frame_rgba()               -> const uint8_t*   (w*h*4, bottom-up)
//   get_frame_width()              -> int
//   get_frame_height()             -> int
//   shutdown()

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  include <GL/gl.h>
#  define EXPORT extern "C" __declspec(dllexport)
#else
#  include <GL/gl.h>
#  include <GL/glx.h>
#  include <X11/Xlib.h>
#  define EXPORT extern "C"
#endif

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <filesystem>

namespace fs = std::filesystem;

// ---------------------------------------------------------------------------
// FBO extension typedefs (not in stock gl.h)
// ---------------------------------------------------------------------------
typedef void   (APIENTRY* PFNGLGENFRAMEBUFFERS)        (GLsizei, GLuint*);
typedef void   (APIENTRY* PFNGLBINDFRAMEBUFFER)        (GLenum,  GLuint);
typedef void   (APIENTRY* PFNGLFRAMEBUFFERTEXTURE2D)   (GLenum,  GLenum, GLenum, GLuint, GLint);
typedef void   (APIENTRY* PFNGLGENRENDERBUFFERS)       (GLsizei, GLuint*);
typedef void   (APIENTRY* PFNGLBINDRENDERBUFFER)       (GLenum,  GLuint);
typedef void   (APIENTRY* PFNGLRENDERBUFFERSTORAGE)    (GLenum,  GLenum, GLsizei, GLsizei);
typedef void   (APIENTRY* PFNGLFRAMEBUFFERRENDERBUFFER)(GLenum,  GLenum, GLenum,  GLuint);
typedef GLenum (APIENTRY* PFNGLCHECKFRAMEBUFFERSTATUS) (GLenum);
typedef void   (APIENTRY* PFNGLDELETEFRAMEBUFFERS)     (GLsizei, const GLuint*);
typedef void   (APIENTRY* PFNGLDELETERENDERBUFFERS)    (GLsizei, const GLuint*);

#define GL_FRAMEBUFFER               0x8D40
#define GL_RENDERBUFFER              0x8D41
#define GL_COLOR_ATTACHMENT0         0x8CE0
#define GL_DEPTH_ATTACHMENT          0x8D00
#define GL_DEPTH_COMPONENT24         0x81A6
#define GL_FRAMEBUFFER_COMPLETE      0x8CD5
#define GL_RGBA8                     0x8058

static PFNGLGENFRAMEBUFFERS         fn_GenFBO    = nullptr;
static PFNGLBINDFRAMEBUFFER         fn_BindFBO   = nullptr;
static PFNGLFRAMEBUFFERTEXTURE2D    fn_FBOTex    = nullptr;
static PFNGLGENRENDERBUFFERS        fn_GenRBO    = nullptr;
static PFNGLBINDRENDERBUFFER        fn_BindRBO   = nullptr;
static PFNGLRENDERBUFFERSTORAGE     fn_RBOStore  = nullptr;
static PFNGLFRAMEBUFFERRENDERBUFFER fn_FBORBO    = nullptr;
static PFNGLCHECKFRAMEBUFFERSTATUS  fn_FBOStatus = nullptr;
static PFNGLDELETEFRAMEBUFFERS      fn_DelFBO    = nullptr;
static PFNGLDELETERENDERBUFFERS     fn_DelRBO    = nullptr;

#ifdef _WIN32
#  define GL_PROC(name) wglGetProcAddress(name)
#else
#  define GL_PROC(name) (void*)glXGetProcAddressARB((const GLubyte*)(name))
#endif

static bool load_fbo_ext() {
#define LOAD(T,var,name) var=(T)GL_PROC(name); if(!var){fprintf(stderr,"[3d] missing %s\n",name);return false;}
    LOAD(PFNGLGENFRAMEBUFFERS,        fn_GenFBO,   "glGenFramebuffers")
    LOAD(PFNGLBINDFRAMEBUFFER,        fn_BindFBO,  "glBindFramebuffer")
    LOAD(PFNGLFRAMEBUFFERTEXTURE2D,   fn_FBOTex,   "glFramebufferTexture2D")
    LOAD(PFNGLGENRENDERBUFFERS,       fn_GenRBO,   "glGenRenderbuffers")
    LOAD(PFNGLBINDRENDERBUFFER,       fn_BindRBO,  "glBindRenderbuffer")
    LOAD(PFNGLRENDERBUFFERSTORAGE,    fn_RBOStore, "glRenderbufferStorage")
    LOAD(PFNGLFRAMEBUFFERRENDERBUFFER,fn_FBORBO,   "glFramebufferRenderbuffer")
    LOAD(PFNGLCHECKFRAMEBUFFERSTATUS, fn_FBOStatus,"glCheckFramebufferStatus")
    LOAD(PFNGLDELETEFRAMEBUFFERS,     fn_DelFBO,   "glDeleteFramebuffers")
    LOAD(PFNGLDELETERENDERBUFFERS,    fn_DelRBO,   "glDeleteRenderbuffers")
#undef LOAD
    return true;
}

// ---------------------------------------------------------------------------
// Math
// ---------------------------------------------------------------------------
struct Vec3 { float x, y, z; };
struct Face { int a, b, c; };
static inline Vec3  operator-(Vec3 a,Vec3 b){return{a.x-b.x,a.y-b.y,a.z-b.z};}
static inline float dot(Vec3 a,Vec3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static inline Vec3  cross(Vec3 a,Vec3 b){return{a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static inline Vec3  norm3(Vec3 v){float l=std::sqrt(dot(v,v));return l>1e-6f?Vec3{v.x/l,v.y/l,v.z/l}:Vec3{};}
static inline float deg2rad(float d){return d*3.14159265f/180.f;}

struct ObjMesh {
    std::vector<Vec3> verts;
    std::vector<Face> faces;
    Vec3  pos{0,0,0}; float scale{1},angle{0},spin_speed{0},r{1},g{1},b{1};
};

// ---------------------------------------------------------------------------
// Platform: hidden offscreen GL context (completely separate from SDL)
// ---------------------------------------------------------------------------
#ifdef _WIN32
static HINSTANCE g_hinst  = nullptr;
static HWND      g_hwnd   = nullptr;
static HDC       g_hdc    = nullptr;
static HGLRC     g_hglrc  = nullptr;

static LRESULT CALLBACK _wndproc(HWND h,UINT m,WPARAM w,LPARAM l){
    return m==WM_CLOSE ? 0 : DefWindowProcA(h,m,w,l);
}

static bool create_offscreen_ctx(int w, int h) {
    g_hinst = GetModuleHandleA(nullptr);
    WNDCLASSA wc{}; wc.style=CS_OWNDC; wc.lpfnWndProc=_wndproc;
    wc.hInstance=g_hinst; wc.lpszClassName="3DeeOffscreen";
    static bool reg=false;
    if(!reg){ RegisterClassA(&wc); reg=true; }

    g_hwnd = CreateWindowExA(0,"3DeeOffscreen","",WS_OVERLAPPEDWINDOW,
                              0,0,w,h,nullptr,nullptr,g_hinst,nullptr);
    if(!g_hwnd) return false;
    ShowWindow(g_hwnd, SW_HIDE);

    g_hdc = GetDC(g_hwnd);
    PIXELFORMATDESCRIPTOR pfd{};
    pfd.nSize=sizeof(pfd); pfd.nVersion=1;
    pfd.dwFlags=PFD_DRAW_TO_WINDOW|PFD_SUPPORT_OPENGL|PFD_DOUBLEBUFFER;
    pfd.iPixelType=PFD_TYPE_RGBA; pfd.cColorBits=32; pfd.cDepthBits=24;
    int fmt=ChoosePixelFormat(g_hdc,&pfd);
    if(fmt<=0||!SetPixelFormat(g_hdc,fmt,&pfd)) return false;
    g_hglrc=wglCreateContext(g_hdc);
    if(!g_hglrc||!wglMakeCurrent(g_hdc,g_hglrc)) return false;
    fprintf(stderr,"[3d] offscreen GL ctx ok: %s\n",glGetString(GL_VENDOR));
    return true;
}
static void destroy_ctx(){
    if(g_hglrc){wglMakeCurrent(nullptr,nullptr);wglDeleteContext(g_hglrc);g_hglrc=nullptr;}
    if(g_hdc&&g_hwnd){ReleaseDC(g_hwnd,g_hdc);g_hdc=nullptr;}
    if(g_hwnd){DestroyWindow(g_hwnd);g_hwnd=nullptr;}
}
static void make_current(){wglMakeCurrent(g_hdc,g_hglrc);}

#else
// Linux: use a Pbuffer or a hidden window for offscreen GL
static Display*   g_dpy  = nullptr;
static GLXContext g_ctx  = nullptr;
static GLXPbuffer g_pbuf = 0;
static GLXWindow  g_glxw = 0;

static bool create_offscreen_ctx(int w, int h){
    g_dpy = XOpenDisplay(nullptr);
    if(!g_dpy){fprintf(stderr,"[3d] XOpenDisplay failed\n");return false;}

    // Try GLX 1.3 Pbuffer first
    typedef GLXFBConfig* (*PFNGLXCHOOSEFBCONFIG)(Display*,int,const int*,int*);
    typedef GLXPbuffer   (*PFNGLXCREATEPBUFFER) (Display*,GLXFBConfig,const int*);
    typedef GLXContext   (*PFNGLXCREATENEWCTX)  (Display*,GLXFBConfig,int,GLXContext,Bool);
    typedef Bool         (*PFNGLXMAKECONTEXTCURRENT)(Display*,GLXDrawable,GLXDrawable,GLXContext);

    auto ChooseFB   =(PFNGLXCHOOSEFBCONFIG)      GL_PROC("glXChooseFBConfig");
    auto CreatePbuf =(PFNGLXCREATEPBUFFER)        GL_PROC("glXCreatePbuffer");
    auto CreateCtx  =(PFNGLXCREATENEWCTX)         GL_PROC("glXCreateNewContext");
    auto MakeCur    =(PFNGLXMAKECONTEXTCURRENT)   GL_PROC("glXMakeContextCurrent");

    if(ChooseFB && CreatePbuf && CreateCtx && MakeCur){
        int fbattrs[]={GLX_RENDER_TYPE,GLX_RGBA_BIT,GLX_DRAWABLE_TYPE,GLX_PBUFFER_BIT,
                       GLX_RED_SIZE,8,GLX_GREEN_SIZE,8,GLX_BLUE_SIZE,8,GLX_DEPTH_SIZE,24,None};
        int n=0;
        GLXFBConfig* cfgs=ChooseFB(g_dpy,0,fbattrs,&n);
        if(cfgs&&n>0){
            int pbattrs[]={GLX_PBUFFER_WIDTH,w,GLX_PBUFFER_HEIGHT,h,None};
            g_pbuf=CreatePbuf(g_dpy,cfgs[0],pbattrs);
            g_ctx =CreateCtx(g_dpy,cfgs[0],GLX_RGBA_TYPE,nullptr,True);
            XFree(cfgs);
            if(g_pbuf&&g_ctx&&MakeCur(g_dpy,g_pbuf,g_pbuf,g_ctx)){
                fprintf(stderr,"[3d] Pbuffer GL ctx ok: %s\n",glGetString(GL_VENDOR));
                return true;
            }
        }
    }

    // Fallback: hidden X window
    int attribs[]={GLX_RGBA,GLX_DEPTH_SIZE,24,GLX_DOUBLEBUFFER,None};
    XVisualInfo* vi=glXChooseVisual(g_dpy,0,attribs);
    if(!vi){fprintf(stderr,"[3d] glXChooseVisual failed\n");return false;}
    Window root=RootWindow(g_dpy,vi->screen);
    XSetWindowAttributes swa{};
    swa.colormap=XCreateColormap(g_dpy,root,vi->visual,AllocNone);
    Window win=XCreateWindow(g_dpy,root,0,0,w,h,0,vi->depth,InputOutput,vi->visual,CWColormap,&swa);
    g_ctx=glXCreateContext(g_dpy,vi,nullptr,True);
    XFree(vi);
    if(!g_ctx||!glXMakeCurrent(g_dpy,win,g_ctx)){fprintf(stderr,"[3d] glXMakeCurrent failed\n");return false;}
    fprintf(stderr,"[3d] hidden-window GL ctx ok: %s\n",glGetString(GL_VENDOR));
    return true;
}
static void destroy_ctx(){
    if(g_ctx){glXMakeCurrent(g_dpy,None,nullptr);glXDestroyContext(g_dpy,g_ctx);g_ctx=nullptr;}
    if(g_dpy){XCloseDisplay(g_dpy);g_dpy=nullptr;}
}
static void make_current(){
    if(g_pbuf) ((Bool(*)(Display*,GLXDrawable,GLXDrawable,GLXContext))GL_PROC("glXMakeContextCurrent"))(g_dpy,g_pbuf,g_pbuf,g_ctx);
    else glXMakeCurrent(g_dpy,(GLXDrawable)g_pbuf,g_ctx); // no-op safe
}
#endif

// ---------------------------------------------------------------------------
// FBO
// ---------------------------------------------------------------------------
static GLuint g_fbo=0, g_fbo_tex=0, g_fbo_rbo=0;
static bool   g_fbo_ok=false;
static int    g_fbo_w=0, g_fbo_h=0;

static void destroy_fbo(){
    if(!g_fbo_ok) return;
    fn_DelFBO(1,&g_fbo); glDeleteTextures(1,&g_fbo_tex); fn_DelRBO(1,&g_fbo_rbo);
    g_fbo=g_fbo_tex=g_fbo_rbo=0; g_fbo_ok=false;
}

static bool create_fbo(int w,int h){
    destroy_fbo();
    glGenTextures(1,&g_fbo_tex);
    glBindTexture(GL_TEXTURE_2D,g_fbo_tex);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glBindTexture(GL_TEXTURE_2D,0);

    fn_GenRBO(1,&g_fbo_rbo);
    fn_BindRBO(GL_RENDERBUFFER,g_fbo_rbo);
    fn_RBOStore(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,w,h);
    fn_BindRBO(GL_RENDERBUFFER,0);

    fn_GenFBO(1,&g_fbo);
    fn_BindFBO(GL_FRAMEBUFFER,g_fbo);
    fn_FBOTex(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,g_fbo_tex,0);
    fn_FBORBO(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,g_fbo_rbo);
    GLenum st=fn_FBOStatus(GL_FRAMEBUFFER);
    fn_BindFBO(GL_FRAMEBUFFER,0);

    if(st!=GL_FRAMEBUFFER_COMPLETE){
        fprintf(stderr,"[3d] FBO incomplete 0x%X\n",(unsigned)st);
        destroy_fbo(); return false;
    }
    g_fbo_w=w; g_fbo_h=h; g_fbo_ok=true;
    fprintf(stderr,"[3d] FBO ok (%dx%d)\n",w,h);
    return true;
}

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------
static int   g_w=800, g_h=600;
static std::vector<ObjMesh>      g_objs;
static std::vector<std::uint8_t> g_pixels;

static float g_cam_x=0,g_cam_y=16,g_cam_z=10,g_pitch=-65,g_fov=60,g_speed=10,g_px=0,g_pz=0;
static Vec3  g_light=norm3({0.4f,1.f,-0.6f});
static float g_ambient=0.25f;

static void setup_camera(){
    glMatrixMode(GL_PROJECTION); glLoadIdentity();
    float asp=(g_h>0)?(float)g_w/(float)g_h:1.f;
    float f=1.f/std::tan(deg2rad(g_fov)*.5f),zn=.1f,zf=1000.f;
    float p[16]={f/asp,0,0,0, 0,f,0,0, 0,0,(zf+zn)/(zn-zf),-1, 0,0,(2*zf*zn)/(zn-zf),0};
    glLoadMatrixf(p);
    glMatrixMode(GL_MODELVIEW); glLoadIdentity();
    glRotatef(g_pitch,1,0,0);
    glTranslatef(-g_cam_x,-g_cam_y,-g_cam_z);
}

static std::string path_str(const fs::path& p){
#if defined(__cpp_char8_t)
    auto u=p.u8string(); std::string s; for(char8_t c:u) s.push_back((char)c); return s;
#else
    return p.u8string();
#endif
}

static bool load_obj_file(const fs::path& path, ObjMesh& out){
    fprintf(stderr,"[3d] loading %s\n",path_str(path).c_str());
    std::ifstream f(path,std::ios::binary);
    if(!f){fprintf(stderr,"[3d] cannot open\n");return false;}
    std::vector<Vec3> rv; std::vector<Face> rf; std::string line;
    while(std::getline(f,line)){
        const char* s=line.c_str();
        while(*s==' '||*s=='\t')++s;
        if(!*s||*s=='#') continue;
        if(s[0]=='v'&&(s[1]==' '||s[1]=='\t')){
            Vec3 v{}; if(sscanf(s+1,"%f %f %f",&v.x,&v.y,&v.z)==3) rv.push_back(v);
        } else if(s[0]=='f'&&(s[1]==' '||s[1]=='\t')){
            std::istringstream ss(s+2); std::string tok; std::vector<int> idx;
            while(ss>>tok){ int i=atoi(tok.c_str()); if(i==0) continue; idx.push_back(i>0?i-1:(int)rv.size()+i); }
            for(int k=1;k+1<(int)idx.size();++k) rf.push_back({idx[0],idx[k],idx[k+1]});
        }
    }
    fprintf(stderr,"[3d] v=%zu f=%zu\n",rv.size(),rf.size());
    if(rv.empty()||rf.empty()) return false;
    Vec3 mn=rv[0],mx=rv[0];
    for(auto& v:rv){mn.x=std::min(mn.x,v.x);mn.y=std::min(mn.y,v.y);mn.z=std::min(mn.z,v.z);
                    mx.x=std::max(mx.x,v.x);mx.y=std::max(mx.y,v.y);mx.z=std::max(mx.z,v.z);}
    Vec3 cen{(mn.x+mx.x)*.5f,(mn.y+mx.y)*.5f,(mn.z+mx.z)*.5f};
    float sz=std::max({mx.x-mn.x,mx.y-mn.y,mx.z-mn.z}); if(sz<1e-6f) sz=1.f;
    out.verts.resize(rv.size());
    for(size_t i=0;i<rv.size();++i) out.verts[i]={(rv[i].x-cen.x)/sz,(rv[i].y-cen.y)/sz,(rv[i].z-cen.z)/sz};
    out.faces=std::move(rf); return true;
}

// ---------------------------------------------------------------------------
// Exported API
// ---------------------------------------------------------------------------
EXPORT int init_renderer(int w, int h){
    g_w=w; g_h=h;
    if(!create_offscreen_ctx(w,h)) return 0;
    if(!load_fbo_ext()) return 0;
    if(!create_fbo(w,h)) return 0;
    g_pixels.resize((size_t)w*h*4);
    return 1;
}

EXPORT void set_viewport(int w,int h){
    if(w<=0||h<=0) return;
    g_w=w; g_h=h;
    make_current();
    create_fbo(w,h);
    g_pixels.resize((size_t)w*h*4);
    glViewport(0,0,w,h);
}

EXPORT int load_obj(const char* fn,float scale,float px,float py,float pz,
                    float angle,float r,float g,float b,float spin){
    ObjMesh m{};
    if(!load_obj_file(fs::u8path(fn),m)) return 0;
    m.scale=scale; m.pos={px,py,pz}; m.angle=angle; m.spin_speed=spin;
    m.r=r/255.f; m.g=g/255.f; m.b=b/255.f;
    g_objs.push_back(std::move(m)); return 1;
}

EXPORT void update(float dt,int kw,int ks,int ka,int kd){
    float mv=g_speed*dt;
    if(kw){g_pz-=mv;g_cam_z-=mv;} if(ks){g_pz+=mv;g_cam_z+=mv;}
    if(ka){g_px-=mv;g_cam_x-=mv;} if(kd){g_px+=mv;g_cam_x+=mv;}
}

EXPORT void render_frame(float /*dt*/){
    make_current();
    fn_BindFBO(GL_FRAMEBUFFER,g_fbo);
    glViewport(0,0,g_w,g_h);
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL);
    glDisable(GL_CULL_FACE); glDisable(GL_DITHER);
    glClearColor(.05f,.05f,.08f,1.f);
    glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
    setup_camera();

    // Ground
    { const float s=10.f;
      glBegin(GL_QUADS); glColor3f(40/255.f,40/255.f,40/255.f);
      glVertex3f(-s,0,-s);glVertex3f(s,0,-s);glVertex3f(s,0,s);glVertex3f(-s,0,s); glEnd();
      glColor3f(80/255.f,80/255.f,80/255.f);
      glBegin(GL_LINE_LOOP);
      glVertex3f(-s,.001f,-s);glVertex3f(s,.001f,-s);glVertex3f(s,.001f,s);glVertex3f(-s,.001f,s); glEnd(); }

    // Player dot
    glPointSize(12.f); glBegin(GL_POINTS); glColor3f(0,200/255.f,1); glVertex3f(g_px,.05f,g_pz); glEnd(); glPointSize(1.f);

    Vec3 cam{g_cam_x,g_cam_y,g_cam_z};
    for(auto& obj:g_objs){
        obj.angle+=obj.spin_speed;
        float ca=std::cos(obj.angle),sa=std::sin(obj.angle);
        std::vector<Vec3> tv(obj.verts.size());
        for(size_t i=0;i<obj.verts.size();++i){
            float vx=obj.verts[i].x,vy=obj.verts[i].y,vz=obj.verts[i].z;
            tv[i]={(vx*ca-vz*sa)*obj.scale+obj.pos.x, vy*obj.scale+obj.pos.y, (vx*sa+vz*ca)*obj.scale+obj.pos.z};
        }
        for(auto& fc:obj.faces){
            const Vec3& v0=tv[fc.a],&v1=tv[fc.b],&v2=tv[fc.c];
            Vec3 n=cross(v1-v0,v2-v0);
            Vec3 c3{(v0.x+v1.x+v2.x)/3.f,(v0.y+v1.y+v2.y)/3.f,(v0.z+v1.z+v2.z)/3.f};
            if(dot(n,cam-c3)<=0.f) continue;
            Vec3 nn=norm3(n);
            float bright=g_ambient+(1.f-g_ambient)*std::max(0.f,dot(nn,g_light));
            glColor3f(obj.r*bright,obj.g*bright,obj.b*bright);
            glBegin(GL_TRIANGLES);
            glVertex3f(v0.x,v0.y,v0.z);glVertex3f(v1.x,v1.y,v1.z);glVertex3f(v2.x,v2.y,v2.z);
            glEnd();
        }
    }
    glFlush();

    // Read pixels out of FBO — Python will blit this as a Surface
    size_t bytes=(size_t)g_w*g_h*4;
    if(g_pixels.size()!=bytes) g_pixels.resize(bytes);
    glPixelStorei(GL_PACK_ALIGNMENT,1);
    glReadPixels(0,0,g_w,g_h,GL_RGBA,GL_UNSIGNED_BYTE,g_pixels.data());
    fn_BindFBO(GL_FRAMEBUFFER,0);
}

EXPORT const std::uint8_t* get_frame_rgba(){ return g_pixels.empty()?nullptr:g_pixels.data(); }
EXPORT int get_frame_width() { return g_w; }
EXPORT int get_frame_height(){ return g_h; }

EXPORT void shutdown(){
    make_current();
    destroy_fbo();
    g_objs.clear(); g_pixels.clear();
    destroy_ctx();
}