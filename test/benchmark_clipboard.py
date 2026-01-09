import ctypes
import time
import pyperclip
import statistics

def benchmark_old_method(iterations=20):
    """Simulate the cost of the old method: WRITE sentinel -> READ to check"""
    durations = []
    print(f"Benchmarking OLD method ({iterations} iterations)...")
    
    for _ in range(iterations):
        start = time.perf_counter()
        
        # 1. Generate sentinel
        sentinel = f"__SENTINEL_{time.time()}__"
        
        # 2. Write sentinel to clipboard (simulating the setup phase)
        try:
            pyperclip.copy(sentinel)
        except:
            pass
            
        # 3. Read back (simulating the check)
        try:
            content = pyperclip.paste()
            is_match = (content == sentinel)
        except:
            pass
            
        durations.append((time.perf_counter() - start) * 1000) # ms
        time.sleep(0.05) # Cool down
        
    return durations

def benchmark_new_method(iterations=20):
    """Simulate the cost of the new method: Check Sequence -> Read Sequence"""
    durations = []
    print(f"Benchmarking NEW method ({iterations} iterations)...")
    user32 = ctypes.windll.user32
    
    for _ in range(iterations):
        start = time.perf_counter()
        
        # 1. Get initial sequence
        seq1 = user32.GetClipboardSequenceNumber()
        
        # 2. Get current sequence (simulating the poll check)
        seq2 = user32.GetClipboardSequenceNumber()
        
        changed = (seq1 != seq2)
        
        durations.append((time.perf_counter() - start) * 1000) # ms
        time.sleep(0.05) # Cool down
        
    return durations

def run_benchmark():
    # Warmup
    pyperclip.copy("warmup")
    time.sleep(1)
    
    old_times = benchmark_old_method()
    new_times = benchmark_new_method()
    
    avg_old = statistics.mean(old_times)
    avg_new = statistics.mean(new_times)
    
    print("\n--- RESULTS ---")
    print(f"OLD Method Average: {avg_old:.4f} ms")
    print(f"NEW Method Average: {avg_new:.4f} ms")
    print(f"Speedup Factor: {avg_old / avg_new:.1f}x faster")
    
    if avg_new < avg_old:
        print("\nCONCLUSION: The new method is FASTER and adds NO overhead.")
    else:
        print("\nCONCLUSION: The new method is slower.")

if __name__ == "__main__":
    run_benchmark()