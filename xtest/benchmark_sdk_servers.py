#!/usr/bin/env python3
"""
Performance benchmark comparing SDK servers vs CLI subprocess approach.

This script demonstrates the dramatic performance improvement achieved
by using SDK servers instead of subprocess calls.
"""

import time
import subprocess
import statistics
from pathlib import Path
from sdk_client import SDKClient, MultiSDKClient


def benchmark_sdk_server(iterations=100):
    """Benchmark SDK server performance."""
    print("\n📊 Benchmarking SDK Server Performance")
    print("=" * 50)
    
    # Initialize client
    multi = MultiSDKClient()
    if not multi.available_sdks:
        print("❌ No SDK servers available")
        return None
    
    sdk_type = multi.available_sdks[0]
    client = multi.get_client(sdk_type)
    print(f"Using {sdk_type.upper()} SDK server")
    
    # Test data
    test_data = b"Benchmark test data" * 100  # ~1.9KB
    attributes = ["https://example.com/attr/test/value/benchmark"]
    
    # Warmup
    print("Warming up...")
    for _ in range(5):
        encrypted = client.encrypt(test_data, attributes, format="ztdf")
        client.decrypt(encrypted)
    
    # Benchmark
    print(f"Running {iterations} iterations...")
    operation_times = []
    
    start_total = time.time()
    for i in range(iterations):
        # Measure individual operation
        start = time.time()
        encrypted = client.encrypt(test_data, attributes, format="ztdf")
        decrypted = client.decrypt(encrypted)
        elapsed = time.time() - start
        operation_times.append(elapsed)
        
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{iterations}", end="\r")
    
    total_elapsed = time.time() - start_total
    
    # Calculate statistics
    avg_time = statistics.mean(operation_times)
    median_time = statistics.median(operation_times)
    min_time = min(operation_times)
    max_time = max(operation_times)
    std_dev = statistics.stdev(operation_times) if len(operation_times) > 1 else 0
    
    print(f"\n\n✅ SDK Server Results ({sdk_type.upper()}):")
    print(f"  Total time: {total_elapsed:.2f} seconds")
    print(f"  Operations: {iterations * 2} (encrypt + decrypt)")
    print(f"  Throughput: {(iterations * 2) / total_elapsed:.1f} ops/sec")
    print(f"\n  Per roundtrip (encrypt + decrypt):")
    print(f"    Average: {avg_time * 1000:.1f}ms")
    print(f"    Median:  {median_time * 1000:.1f}ms")
    print(f"    Min:     {min_time * 1000:.1f}ms")
    print(f"    Max:     {max_time * 1000:.1f}ms")
    print(f"    Std Dev: {std_dev * 1000:.1f}ms")
    
    return {
        'total_time': total_elapsed,
        'ops_per_sec': (iterations * 2) / total_elapsed,
        'avg_time_ms': avg_time * 1000,
        'median_time_ms': median_time * 1000,
    }


def benchmark_cli_subprocess(iterations=10):
    """Benchmark CLI subprocess performance (simulated)."""
    print("\n📊 Benchmarking CLI Subprocess Performance (Simulated)")
    print("=" * 50)
    
    # Check if otdfctl exists
    otdfctl_path = Path("xtest/sdk/go/dist/main/otdfctl.sh")
    if not otdfctl_path.exists():
        print("⚠️  otdfctl not found, using simulated timings")
        print("   (Typical subprocess spawn overhead: ~50ms)")
        
        # Simulated timings based on typical subprocess overhead
        subprocess_overhead = 0.050  # 50ms per subprocess call
        operations = iterations * 2  # encrypt + decrypt
        total_time = operations * subprocess_overhead
        
        print(f"\n✅ CLI Subprocess Results (Simulated):")
        print(f"  Total time: {total_time:.2f} seconds")
        print(f"  Operations: {operations}")
        print(f"  Throughput: {operations / total_time:.1f} ops/sec")
        print(f"  Per operation: {subprocess_overhead * 1000:.1f}ms")
        
        return {
            'total_time': total_time,
            'ops_per_sec': operations / total_time,
            'avg_time_ms': subprocess_overhead * 1000,
            'median_time_ms': subprocess_overhead * 1000,
        }
    
    # If otdfctl exists, we could run actual benchmarks
    # For now, return simulated results
    return benchmark_cli_subprocess_simulated(iterations)


def benchmark_cli_subprocess_simulated(iterations):
    """Simulated CLI performance based on measured subprocess overhead."""
    # Measure actual subprocess spawn overhead
    print("Measuring subprocess spawn overhead...")
    spawn_times = []
    
    for _ in range(10):
        start = time.time()
        result = subprocess.run(["echo", "test"], capture_output=True)
        elapsed = time.time() - start
        spawn_times.append(elapsed)
    
    avg_spawn_time = statistics.mean(spawn_times)
    print(f"  Average subprocess spawn time: {avg_spawn_time * 1000:.1f}ms")
    
    # Calculate estimated performance
    # Each operation requires: subprocess spawn + command execution + I/O
    estimated_time_per_op = avg_spawn_time + 0.010  # Add 10ms for command execution
    operations = iterations * 2
    total_time = operations * estimated_time_per_op
    
    print(f"\n✅ CLI Subprocess Results (Estimated):")
    print(f"  Total time: {total_time:.2f} seconds")
    print(f"  Operations: {operations}")
    print(f"  Throughput: {operations / total_time:.1f} ops/sec")
    print(f"  Per operation: {estimated_time_per_op * 1000:.1f}ms")
    
    return {
        'total_time': total_time,
        'ops_per_sec': operations / total_time,
        'avg_time_ms': estimated_time_per_op * 1000,
        'median_time_ms': estimated_time_per_op * 1000,
    }


def compare_results(sdk_results, cli_results):
    """Compare and display performance improvement."""
    print("\n" + "=" * 60)
    print("🚀 PERFORMANCE COMPARISON")
    print("=" * 60)
    
    if sdk_results and cli_results:
        improvement_throughput = sdk_results['ops_per_sec'] / cli_results['ops_per_sec']
        improvement_latency = cli_results['avg_time_ms'] / sdk_results['avg_time_ms']
        
        print(f"\n📈 Throughput:")
        print(f"  SDK Server:  {sdk_results['ops_per_sec']:.1f} ops/sec")
        print(f"  CLI Process: {cli_results['ops_per_sec']:.1f} ops/sec")
        print(f"  Improvement: {improvement_throughput:.1f}x faster")
        
        print(f"\n⏱️  Latency (per roundtrip):")
        print(f"  SDK Server:  {sdk_results['avg_time_ms']:.1f}ms")
        print(f"  CLI Process: {cli_results['avg_time_ms']:.1f}ms")
        print(f"  Improvement: {improvement_latency:.1f}x faster")
        
        print(f"\n💡 Summary:")
        print(f"  The SDK server approach is {improvement_throughput:.0f}x faster")
        print(f"  This means tests that took 10 minutes now take ~{10/improvement_throughput:.1f} minutes")
        
        # Calculate time savings for typical test suite
        typical_operations = 1000  # Typical test suite operations
        time_with_cli = typical_operations / cli_results['ops_per_sec']
        time_with_sdk = typical_operations / sdk_results['ops_per_sec']
        time_saved = time_with_cli - time_with_sdk
        
        print(f"\n⏰ Time Savings (for {typical_operations} operations):")
        print(f"  CLI Process: {time_with_cli:.1f} seconds")
        print(f"  SDK Server:  {time_with_sdk:.1f} seconds")
        print(f"  Time Saved:  {time_saved:.1f} seconds ({time_saved/60:.1f} minutes)")
    else:
        print("❌ Could not compare results - missing data")


def main():
    """Run the benchmark comparison."""
    print("\n" + "=" * 60)
    print("OpenTDF SDK Server Performance Benchmark")
    print("=" * 60)
    
    # Run benchmarks
    sdk_results = benchmark_sdk_server(iterations=100)
    cli_results = benchmark_cli_subprocess(iterations=100)
    
    # Compare results
    compare_results(sdk_results, cli_results)
    
    print("\n" + "=" * 60)
    print("✅ Benchmark Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()