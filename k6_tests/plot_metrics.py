import pandas as pd
import matplotlib.pyplot as plt
import sys
import matplotlib.ticker as ticker

if len(sys.argv) < 2:
    print("Usage: python plot_metrics.py <path_to_csv>")
    sys.exit(1)

file_path = sys.argv[1]
# Bezpieczne wyodrębnienie samej nazwy testu
test_name = file_path.split('/')[-1].replace('_metrics.csv', '')

try:
    df = pd.read_csv(file_path)
    # Konwersja tekstowego czasu na obiekty daty
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='%H:%M:%S')
    
    # 1. NORMALIZACJA CZASU: Obliczanie minut od startu testu (T=0)
    start_time = df['timestamp'].iloc[0]
    df['time_minutes'] = (df['timestamp'] - start_time).dt.total_seconds() / 60.0
    
    # 2. NORMALIZACJA RDZENI: Konwersja milirdzeni (1000m) na pełne rdzenie (1.0 Core)
    df['cpu_cores'] = df['cpu_millicores'] / 1000.0
    
except Exception as e:
    print(f"Error loading CSV: {e}")
    sys.exit(1)

# Tworzenie siatki 4 pod-wykresów z jedną wspólną osią czasu
fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(14, 18), sharex=True)
fig.suptitle(f'Comprehensive Cluster Load: {test_name.upper()}', fontsize=18)

# 1. CPU
ax1.plot(df['time_minutes'], df['cpu_cores'], color='tab:red', linewidth=2)
ax1.set_ylabel('CPU Usage (Cores)', fontsize=12)
ax1.grid(True, linestyle='--', alpha=0.7)
ax1.set_title('CPU Allocation (Normalized)')

# 2. RAM
ax2.plot(df['time_minutes'], df['memory_mb'], color='tab:blue', linewidth=2)
ax2.set_ylabel('RAM (MB)', fontsize=12)
ax2.grid(True, linestyle='--', alpha=0.7)
ax2.set_title('Memory Allocation')

# 3. Sieć (Rx vs Tx)
ax3.plot(df['time_minutes'], df['net_rx_kbps'], label='Net RX (Download)', color='tab:green', linewidth=2)
ax3.plot(df['time_minutes'], df['net_tx_kbps'], label='Net TX (Upload)', color='tab:orange', linewidth=2)
ax3.set_ylabel('Network (KB/s)', fontsize=12)
ax3.grid(True, linestyle='--', alpha=0.7)
ax3.legend(loc='upper right')
ax3.set_title('Network I/O Throughput')

# 4. Dysk (Read vs Write)
ax4.plot(df['time_minutes'], df['disk_read_kbps'], label='Disk Read', color='tab:purple', linewidth=2)
ax4.plot(df['time_minutes'], df['disk_write_kbps'], label='Disk Write', color='tab:brown', linewidth=2)
ax4.set_ylabel('Disk (KB/s)', fontsize=12)
ax4.set_xlabel('Time (Minutes from start)', fontsize=12)
ax4.grid(True, linestyle='--', alpha=0.7)
ax4.legend(loc='upper right')
ax4.set_title('Filesystem I/O')

# Wymuszenie czytelnych znaczników (ticków) na osi X - co równe 5 minut
ax4.xaxis.set_major_locator(ticker.MultipleLocator(base=5.0))
ax4.xaxis.set_minor_locator(ticker.MultipleLocator(base=1.0))

plt.tight_layout()

# Zapis pliku w katalogu results/
output_filename = f'results/{test_name}_full_dashboard.png'
plt.savefig(output_filename, dpi=300)
print(f"Successfully generated comprehensive plot: {output_filename}")
