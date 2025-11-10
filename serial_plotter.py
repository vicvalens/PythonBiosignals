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

BUFFER_LEN = 500  # muestras visibles

class SerialPlotterMin(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Serial Plotter - Minimal + AutoY/DC/Smooth")
        self.geometry("860x520")

        # Estado
        self.ser = None
        self.reader_thread = None
        self.stop_event = threading.Event()
        self.buffer = deque([0.0]*BUFFER_LEN, maxlen=BUFFER_LEN)
        self.connected = False

        # --- UI superior ---
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="COM:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=20)
        self.port_cb['values'] = self._scan_ports()
        if self.port_cb['values']:
            self.port_cb.current(0)
        else:
            self.port_var.set("COM3 / /dev/ttyACM0")
        self.port_cb.pack(side="left", padx=4)

        ttk.Label(top, text="Baud:").pack(side="left")
        self.baud_var = tk.StringVar(value="115200")
        ttk.Entry(top, textvariable=self.baud_var, width=8).pack(side="left", padx=4)

        self.connect_btn = ttk.Button(top, text="Conectar", command=self.toggle)
        self.connect_btn.pack(side="left", padx=8)

        # Controles de visualización (mínimos)
        self.auto_y = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto Y", variable=self.auto_y).pack(side="left", padx=(10,2))

        self.rm_dc = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Quitar DC", variable=self.rm_dc).pack(side="left", padx=(10,2))

        ttk.Label(top, text="Suave (N):").pack(side="left", padx=(10,2))
        self.smooth_n = tk.IntVar(value=5)  # 1 = sin suavizado
        ttk.Entry(top, textvariable=self.smooth_n, width=5).pack(side="left", padx=(0,8))

        # --- Gráfica ---
        fig = Figure(figsize=(7.8, 3.6), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("Raw Signal")
        self.ax.set_xlabel("muestras recientes")
        self.ax.set_ylabel("amplitud")
        self.ax.set_xlim(0, BUFFER_LEN-1)
        self.ax.set_ylim(0, 1023)  # solo se usa si Auto Y está desactivado
        (self.line,) = self.ax.plot(range(BUFFER_LEN), list(self.buffer), lw=1)
        self.ax.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        # Refresco de gráfica
        self.after(40, self._tick)

        # Cierre limpio
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Serial ----------
    def _scan_ports(self):
        if not HAS_SERIAL:
            return []
        return [p.device for p in list_ports.comports()]

    def toggle(self):
        if self.connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        if not HAS_SERIAL:
            messagebox.showerror("Serial", "Instala pyserial: pip install pyserial")
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showinfo("Puerto", "Escribe o selecciona un COM.")
            return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror("Baud", "Baud inválido.")
            return

        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=1)
            time.sleep(0.3)  # estabilizar
        except Exception as e:
            messagebox.showerror("Conexión", f"No se pudo abrir {port}:\n{e}")
            self.ser = None
            return

        self.stop_event.clear()
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()
        self.connected = True
        self.connect_btn.config(text="Desconectar")
        self.ax.set_title(f"Raw Signal ({port} @ {baud})")

    def disconnect(self):
        self.stop_event.set()
        self.connected = False
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.connect_btn.config(text="Conectar")
        self.ax.set_title("Raw Signal")
        self.canvas.draw_idle()

    def _reader(self):
        with self.ser:
            while not self.stop_event.is_set():
                try:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    val = float(line)  # int o float por línea
                    self.buffer.append(val)
                except ValueError:
                    continue
                except Exception:
                    break
        self.connected = False
        self.connect_btn.config(text="Conectar")

    # ---------- Utils de señal ----------
    def _get_processed(self):
        """Devuelve una lista procesada (opcional DC y suavizado)."""
        data = list(self.buffer)

        # Quitar DC (resta la media) para centrar la onda
        if self.rm_dc.get() and data:
            mean = statistics.fmean(data)
            data = [d - mean for d in data]

        # Suavizado (media móvil de ventana N)
        N = max(1, int(self.smooth_n.get() or 1))
        if N > 1 and len(data) >= N:
            out = []
            acc = sum(data[:N])
            out.append(acc / N)
            for i in range(N, len(data)):
                acc += data[i] - data[i - N]
                out.append(acc / N)
            # para mantener el mismo largo, completa al inicio
            pad = [out[0]] * (len(data) - len(out))
            data = pad + out

        return data

    # ---------- Gráfica ----------
    def _tick(self):
        y = self._get_processed()
        if not y:
            self.after(40, self._tick); return

        # Auto Y: ajusta a min/max con margen
        if self.auto_y.get():
            y_min, y_max = min(y), max(y)
            if y_max == y_min:
                y_max = y_min + 1.0
            span = y_max - y_min
            pad = max(1.0, span * 0.15)
            self.ax.set_ylim(y_min - pad, y_max + pad)
        # Si no hay Auto Y, se conserva el ylim actual

        self.line.set_ydata(y)
        self.canvas.draw_idle()
        self.after(40, self._tick)

    # ---------- Cierre ----------
    def on_close(self):
        self.disconnect()
        self.destroy()

if __name__ == "__main__":
    SerialPlotterMin().mainloop()
