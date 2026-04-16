"""
Multi-threaded game manager.
Handles separate threads for physics, world updates, RPC, and enemy rendering.
"""

import threading
import queue
import time
from typing import Optional, Callable


class ThreadManager:
    """Manages multiple worker threads with queued commands."""
    
    def __init__(self):
        self.threads = {}
        self.queues = {}
        self.running = False
        self.workers = {}
    
    def create_worker(self, name: str, worker_func: Callable, args: tuple = ()):
        """
        Create and start a worker thread.
        
        Args:
            name: Thread identifier
            worker_func: Function to run in thread
            args: Arguments to pass to worker_func
        """
        if name in self.threads:
            return
        
        task_queue = queue.Queue()
        self.queues[name] = task_queue
        
        thread = threading.Thread(
            target=self._worker_loop,
            args=(name, worker_func, task_queue, args),
            daemon=True,
            name=f"Worker-{name}"
        )
        thread.start()
        self.threads[name] = thread
    
    def _worker_loop(self, name: str, worker_func: Callable, 
                     task_queue: queue.Queue, args: tuple):
        """Main loop for worker threads."""
        try:
            worker_func(task_queue, *args)
        except Exception as e:
            print(f"Worker {name} error: {e}")
            import traceback
            traceback.print_exc()
    
    def queue_task(self, worker_name: str, task: dict):
        """
        Queue a task for a worker thread.
        
        Args:
            worker_name: Name of the worker thread
            task: Dict with task data
        """
        if worker_name in self.queues:
            self.queues[worker_name].put(task)
    
    def get_queue(self, worker_name: str) -> Optional[queue.Queue]:
        """Get the task queue for a worker."""
        return self.queues.get(worker_name)
    
    def stop_all(self):
        """Signal all workers to stop."""
        self.running = False
        for q in self.queues.values():
            q.put({'type': 'stop'})


class PhysicsWorker:
    """Worker for physics calculations."""
    
    def __init__(self, world_loader, dt_sync: queue.Queue = None):
        self.world_loader = world_loader
        self.dt_sync = dt_sync or queue.Queue()
        self.last_update = time.time()
        self.world_lock = getattr(world_loader, '_thread_lock', threading.Lock())
    
    def run(self, task_queue: queue.Queue):
        """Main physics worker loop."""
        while True:
            try:
                task = task_queue.get(timeout=0.016)  # 60 FPS
                
                if task.get('type') == 'stop':
                    break
                elif task.get('type') == 'update':
                    dt = task.get('dt', 0.016)
                    if self.world_loader:
                        with self.world_lock:
                            self.world_loader.update_physics(dt)
                elif task.get('type') == 'set_dt':
                    # For frame timing sync
                    self.dt_sync.put(task.get('dt'))
                    
            except queue.Empty:
                # Update with default timestep if no task
                if self.world_loader:
                    try:
                        with self.world_lock:
                            self.world_loader.update_physics(0.016)
                    except Exception:
                        pass
            except Exception as e:
                print(f"PhysicsWorker error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.01)


class RPCWorker:
    """Worker for Discord RPC updates."""
    
    def __init__(self, rpc, update_interval: float = 1.0):
        self.rpc = rpc
        self.update_interval = update_interval
        self.last_update = time.time()
        self.current_state = {}
    
    def run(self, task_queue: queue.Queue):
        """Main RPC worker loop."""
        while True:
            try:
                task = task_queue.get(timeout=self.update_interval)
                
                if task.get('type') == 'stop':
                    break
                elif task.get('type') == 'update':
                    self._update_rpc(task)
                    
            except queue.Empty:
                # Periodically maintain connection
                if self.rpc and hasattr(self.rpc, 'update'):
                    try:
                        self.rpc.update()
                    except:
                        pass
    
    def _update_rpc(self, state_dict: dict):
        """Update RPC with new state."""
        if not self.rpc:
            return
        
        try:
            # Only update if state changed to reduce API calls
            if state_dict != self.current_state:
                self.rpc.update(
                    state=state_dict.get('state', 'Playing'),
                    details=state_dict.get('details', ''),
                    large_image=state_dict.get('large_image', ''),
                    large_text=state_dict.get('large_text', '')
                )
                self.current_state = state_dict.copy()
        except Exception as e:
            print(f"RPC update error: {e}")


class EnemyRenderWorker:
    """Worker for enemy rendering (batching enemy draw calls)."""
    
    def __init__(self, render_helper):
        self.render_helper = render_helper
        self.enemy_queue = []
    
    def run(self, task_queue: queue.Queue):
        """Main enemy render worker loop."""
        while True:
            try:
                task = task_queue.get(timeout=0.016)
                
                if task.get('type') == 'stop':
                    break
                elif task.get('type') == 'render_enemy':
                    self._queue_enemy_render(task)
                elif task.get('type') == 'flush':
                    self._flush_enemy_renders()
                    
            except queue.Empty:
                pass
    
    def _queue_enemy_render(self, task: dict):
        """Queue an enemy to be rendered."""
        self.enemy_queue.append(task)
    
    def _flush_enemy_renders(self):
        """Render all queued enemies."""
        for task in self.enemy_queue:
            try:
                enemy = task.get('enemy')
                surface = task.get('surface')
                cam_x = task.get('cam_x', 0)
                cam_y = task.get('cam_y', 0)
                
                if enemy and hasattr(enemy, 'draw_in_world'):
                    enemy.draw_in_world(surface, cam_x, cam_y)
            except Exception as e:
                print(f"Enemy render error: {e}")
        
        self.enemy_queue.clear()


class WorldWorker:
    """Worker for world updates and state management."""
    
    def __init__(self, world_loader):
        self.world_loader = world_loader
        self.world_lock = getattr(world_loader, '_thread_lock', threading.Lock())
    
    def run(self, task_queue: queue.Queue):
        """Main world worker loop."""
        while True:
            try:
                task = task_queue.get(timeout=0.016)
                
                if task.get('type') == 'stop':
                    break
                elif task.get('type') == 'update':
                    dt = task.get('dt', 0.016)
                    if self.world_loader:
                        try:
                            with self.world_lock:
                                # Update world state (not physics, not rendering)
                                if hasattr(self.world_loader, 'update'):
                                    self.world_loader.update(dt)
                        except Exception:
                            pass
                elif task.get('type') == 'load_chunk':
                    # Async chunk loading
                    if self.world_loader and hasattr(self.world_loader, 'load_chunk'):
                        try:
                            with self.world_lock:
                                self.world_loader.load_chunk(task.get('chunk_idx'))
                        except Exception:
                            pass
                    
            except queue.Empty:
                pass
            except Exception as e:
                print(f"WorldWorker error: {e}")
                time.sleep(0.01)
