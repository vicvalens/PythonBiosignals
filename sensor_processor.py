import threading, time, statistics
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Serial
try:
    import serial
    import serial.tools.list_ports as list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False
    serial = None
    list_ports = None

BUFFER_LEN = 500  # muestras visibles

class SerialPlotterRange(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Raw Signal + Range Control (ON/OFF)")
        self.geometry("960x560")

        # Estado
        self.ser = None
        self.reader_thread = None
        self.stop_event = threading.Event()
        self.buffer = deque([0.0]*BUFFER_LEN, maxlen=BUFFER_LEN)
        self.connected = False
        self.last_sent = None   # recuerda último '1'/'0' para no saturar

        # ---- Barra superior ----
        top = ttk.Frame(self, padding=8); top.pack(fill="x")

        ttk.Label(top, text="COM:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=22)
        self.port_cb["values"] = self._scan_ports()
        if self.port_cb["values"]:
            self.port_cb.current(0)
        else:
            self.port_var.set("COM3 / /dev/ttyACM0")
        self.port_cb.pack(side="left", padx=4)

        ttk.Label(top, text="Baud:").pack(side="left")
        self.baud_var = tk.StringVar(value="115200")
        ttk.Entry(top, textvariable=self.baud_var, width=8).pack(side="left", padx=4)

        self.connect_btn = ttk.Button(top, text="Connect", command=self.toggle)
        self.connect_btn.pack(side="left", padx=8)

        # Visualización/Procesamiento
        self.auto_y = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto Y", variable=self.auto_y).pack(side="left", padx=(10,2))

        self.rm_dc = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Remove DC", variable=self.rm_dc).pack(side="left", padx=(10,2))

        ttk.Label(top, text="Smooth N:").pack(side="left", padx=(10,2))
        self.smooth_n = tk.IntVar(value=5)  # 1 = sin suavizado
        ttk.Entry(top, textvariable=self.smooth_n, width=5).pack(side="left", padx=(0,8))

        # Control por rango
        ctrl = ttk.Frame(self, padding=(8,0)); ctrl.pack(fill="x")
        ttk.Label(ctrl, text="LOW:").pack(side="left")
        self.low_var = tk.DoubleVar(value=-50.0)
        ttk.Entry(ctrl, textvariable=self.low_var, width=8).pack(side="left", padx=(2,8))

        ttk.Label(ctrl, text="HIGH:").pack(side="left")
        self.high_var = tk.DoubleVar(value=50.0)
        ttk.Entry(ctrl, textvariable=self.high_var, width=8).pack(side="left", padx=(2,12))

        self.enable_ctl = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Enable control (send 1/0)", variable=self.enable_ctl).pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="LED: (no control)")
        ttk.Label(ctrl, textvariable=self.status_var).pack(side="left", padx=12)

        # ---- Gráfica ----
        fig = Figure(figsize=(8.8, 3.8), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("Raw Signal")
        self.ax.set_xlabel("recent samples")
        self.ax.set_ylabel("amplitude")
        self.ax.set_xlim(0, BUFFER_LEN-1)
        self.ax.set_ylim(0, 1023)
        (self.line,) = self.ax.plot(range(BUFFER_LEN), list(self.buffer), lw=1)
        self.ax.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        # Loops
        self.after(40, self._tick)          # refresco de gráfica
        self.after(80, self._control_tick)  # envío ON/OFF según rango

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Serial ----------
    def _scan_ports(self):
        if not HAS_SERIAL: return []
        return [p.device for p in list_ports.comports()]

    def toggle(self):
        if self.connected: self.disconnect()
        else:              self.connect()

    def connect(self):
        if not HAS_SERIAL:
            messagebox.showerror("Serial", "Install pyserial: pip install pyserial")
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showinfo("Port", "Select or type a COM port.")
            return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror("Baud", "Invalid baud.")
            return
        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=1)
            time.sleep(0.3)
        except Exception as e:
            messagebox.showerror("Connect", f"Cannot open {port}:\n{e}")
            self.ser = None
            return

        self.stop_event.clear()
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()
        self.connected = True
        self.connect_btn.config(text="Disconnect")
        self.ax.set_title(f"Raw Signal ({port} @ {baud})")
        self.last_sent = None

    def disconnect(self):
        self.stop_event.set()
        self.connected = False
        try:
            if self.ser and self.ser.is_open: self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.connect_btn.config(text="Connect")
        self.ax.set_title("Raw Signal")
        self.canvas.draw_idle()

    def _reader(self):
        with self.ser:
            while not self.stop_event.is_set():
                try:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if not line: continue
                    val = float(line)   # int o float por línea
                    self.buffer.append(val)
                except ValueError:
                    continue
                except Exception:
                    break
        self.connected = False
        self.connect_btn.config(text="Connect")

    # ---------- Procesamiento simple ----------
    def _get_processed(self):
        data = list(self.buffer)
        if not data: return data

        # Quitar DC (centrar en 0)
        if self.rm_dc.get():
            mean = statistics.fmean(data)
            data = [d - mean for d in data]

        # Suavizado (media móvil)
        N = max(1, int(self.smooth_n.get() or 1))
        if N > 1 and len(data) >= N:
            out = []
            acc = sum(data[:N]); out.append(acc / N)
            for i in range(N, len(data)):
                acc += data[i] - data[i - N]
                out.append(acc / N)
            data = [out[0]] * (len(data) - len(out)) + out

        return data

    # ---------- Gráfica ----------
    def _tick(self):
        y = self._get_processed()
        if y:
            if self.auto_y.get():
                y_min, y_max = min(y), max(y)
                if y_max == y_min: y_max = y_min + 1.0
                span = y_max - y_min; pad = max(1.0, span * 0.15)
                self.ax.set_ylim(y_min - pad, y_max + pad)
            self.line.set_ydata(y)
        self.canvas.draw_idle()
        self.after(40, self._tick)

    # ---------- Control por rango ----------
    def _control_tick(self):
        if self.enable_ctl.get() and self.connected and self.ser is not None:
            y = self._get_processed()
            if y:
                try:
                    low = float(self.low_var.get())
                    high = float(self.high_var.get())
                    if low > high: low, high = high, low
                except ValueError:
                    low, high = -50.0, 50.0

                val = y[-1]  # último valor (centrado y suavizado según opciones)
                want = '1' if (val >= low and val <= high) else '0'

                if want != self.last_sent:
                    try:
                        self.ser.write(want.encode())  # enviar '1' o '0'
                        self.last_sent = want
                        self.status_var.set(f"LED: {'ON' if want=='1' else 'OFF'}  (val={val:.1f}, range=[{low},{high}])")
                    except Exception:
                        pass
        self.after(80, self._control_tick)  # ~12.5 Hz de decisión

    # ---------- Cierre ----------
    def on_close(self):
        self.disconnect()
        self.destroy()

if __name__ == "__main__":
    SerialPlotterRange().mainloop()
