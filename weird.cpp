// renderer.cpp
// Compile on Linux:   g++ -shared -fPIC -o renderer.so renderer.cpp -lGL -lX11
// Compile on Windows: g++ -shared -o renderer.dll renderer.cpp -lopengl32 -lgdi32

#ifdef _WIN32
  #include <windows.h>
  #include <GL/gl.h>
#else
  #include <GL/gl.h>
  #include <GL/glx.h>
  #include <X11/Xlib.h>
#endif

#include <math.h>

// ---------- platform context ----------

#ifdef _WIN32
static HDC   g_hdc  = nullptr;
static HGLRC g_hglrc = nullptr;

extern "C" __declspec(dllexport)
int init_gl(void* hwnd_ptr) {
    HWND hwnd = (HWND)hwnd_ptr;
    g_hdc = GetDC(hwnd);

    PIXELFORMATDESCRIPTOR pfd = {};
    pfd.nSize      = sizeof(pfd);
    pfd.nVersion   = 1;
    pfd.dwFlags    = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cDepthBits = 24;

    int fmt = ChoosePixelFormat(g_hdc, &pfd);
    SetPixelFormat(g_hdc, fmt, &pfd);

    g_hglrc = wglCreateContext(g_hdc);
    wglMakeCurrent(g_hdc, g_hglrc);
    return 1;
}

extern "C" __declspec(dllexport)
void swap_buffers() {
    SwapBuffers(g_hdc);
}

#else
// ---------- Linux / X11 ----------
static Display*  g_display = nullptr;
static GLXContext g_ctx    = nullptr;
static Window    g_window  = 0;

extern "C"
int init_gl(void* display_ptr, unsigned long window_id) {
    g_display = (Display*)display_ptr;
    g_window  = (Window)window_id;

    int attribs[] = { GLX_RGBA, GLX_DEPTH_SIZE, 24, GLX_DOUBLEBUFFER, None };
    XVisualInfo* vi = glXChooseVisual(g_display, 0, attribs);
    if (!vi) return 0;

    g_ctx = glXCreateContext(g_display, vi, nullptr, GL_TRUE);
    glXMakeCurrent(g_display, g_window, g_ctx);
    XFree(vi);
    return 1;
}

extern "C"
void swap_buffers() {
    glXSwapBuffers(g_display, g_window);
}
#endif

// ---------- shared rendering code (same on all platforms) ----------

static float g_angle = 0.0f;
static int   g_width = 800;
static int   g_height = 600;

extern "C"
#ifdef _WIN32
__declspec(dllexport)
#endif
void set_viewport(int w, int h) {
    g_width  = w;
    g_height = h;
    glViewport(0, 0, w, h);
}

extern "C"
#ifdef _WIN32
__declspec(dllexport)
#endif
void render_frame(float dt) {
    g_angle += dt * 90.0f;   // degrees per second

    glClearColor(0.05f, 0.05f, 0.1f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    glEnable(GL_DEPTH_TEST);

    // --- projection ---
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    float aspect = (float)g_width / (float)g_height;
    float fov    = 60.0f * (3.14159f / 180.0f);
    float near_p = 0.1f, far_p = 100.0f;
    float f = 1.0f / tanf(fov / 2.0f);
    float proj[16] = {
        f/aspect, 0,  0,                              0,
        0,        f,  0,                              0,
        0,        0, (far_p+near_p)/(near_p-far_p),  -1,
        0,        0, (2*far_p*near_p)/(near_p-far_p), 0
    };
    glLoadMatrixf(proj);

    // --- modelview ---
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    // camera pulled back
    glTranslatef(0, 0, -4.0f);
    glRotatef(g_angle, 1, 1, 0);   // spin on X and Y

    // --- spinning RGB cube ---
    glBegin(GL_QUADS);

    // front  - red
    glColor3f(1,0,0);
    glVertex3f(-1,-1, 1); glVertex3f( 1,-1, 1);
    glVertex3f( 1, 1, 1); glVertex3f(-1, 1, 1);

    // back   - cyan
    glColor3f(0,1,1);
    glVertex3f(-1,-1,-1); glVertex3f(-1, 1,-1);
    glVertex3f( 1, 1,-1); glVertex3f( 1,-1,-1);

    // left   - green
    glColor3f(0,1,0);
    glVertex3f(-1,-1,-1); glVertex3f(-1,-1, 1);
    glVertex3f(-1, 1, 1); glVertex3f(-1, 1,-1);

    // right  - magenta
    glColor3f(1,0,1);
    glVertex3f( 1,-1,-1); glVertex3f( 1, 1,-1);
    glVertex3f( 1, 1, 1); glVertex3f( 1,-1, 1);

    // top    - blue
    glColor3f(0,0,1);
    glVertex3f(-1, 1,-1); glVertex3f(-1, 1, 1);
    glVertex3f( 1, 1, 1); glVertex3f( 1, 1,-1);

    // bottom - yellow
    glColor3f(1,1,0);
    glVertex3f(-1,-1,-1); glVertex3f( 1,-1,-1);
    glVertex3f( 1,-1, 1); glVertex3f(-1,-1, 1);

    glEnd();

    swap_buffers();
}