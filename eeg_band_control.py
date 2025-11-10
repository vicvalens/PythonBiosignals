import time, threading
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.gridspec import GridSpec

# ---- Serial (pyserial) ----
try:
    import serial
    import serial.tools.list_ports as list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False
    serial = None
    list_ports = None

# ===== Parámetros =====
BUFFER_SEC_DEFAULT = 8.0
FS_DEFAULT = 100.0
WIN_SEC_DEFAULT = 2.0
SMOOTH_N_DEFAULT = 5
AUTOY_DEFAULT = True

BANDS_DEFAULT = {
    "Delta": (0.5, 4.0),
    "Theta": (4.0, 8.0),
    "Alpha": (8.0, 12.0),
    "Beta":  (12.0, 30.0),
    "Gamma": (30.0, 45.0),
}
TOTAL_BAND = (1.0, 45.0)

# Colores (HEX) compatibles con Tk y Matplotlib
BAND_COLORS = {
    "Delta": "#9467bd",  # purple
    "Theta": "#bcbd22",  # olive
    "Alpha": "#2ca02c",  # green
    "Beta":  "#d62728",  # red
    "Gamma": "#17becf",  # cyan
}
TIME_COLOR = "#1f77b4"   # blue
PSD_COLOR  = "#ff7f0e"   # orange

class EEGBandControl(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EEG Band Control (wide band panel, bars/lines)")
        self.geometry("1240x780")

        # Serial / estado
        self.ser = None
        self.reader_thread = None
        self.stop_event = threading.Event()
        self.connected = False

        # Parámetros
        self.fs = tk.DoubleVar(value=FS_DEFAULT)
        self.win_sec = tk.DoubleVar(value=WIN_SEC_DEFAULT)
        self.smooth_n = tk.IntVar(value=SMOOTH_N_DEFAULT)
        self.auto_y = tk.BooleanVar(value=AUTOY_DEFAULT)
        self.rm_dc = tk.BooleanVar(value=True)
        self.zscore_vis = tk.BooleanVar(value=True)

        # Control LED
        self.band_names = ["Delta", "Theta", "Alpha", "Beta", "Gamma"]
        self.selected_band = tk.StringVar(value="Alpha")
        self.threshold = tk.DoubleVar(value=0.30)
        self.direction = tk.StringVar(value=">=")
        self.enable_ctl = tk.BooleanVar(value=False)
        self.last_sent = None

        # Rango de bandas
        self.band_vars = {}
        for k, (lo, hi) in BANDS_DEFAULT.items():
            self.band_vars[k] = (tk.DoubleVar(value=lo), tk.DoubleVar(value=hi))

        # Historial de bandas (para líneas)
        self.lines_mode = tk.BooleanVar(value=False)   # toggle barras ↔ líneas
        self.band_hist_len = 200
        self.band_hist = {k: deque([0.0]*self.band_hist_len, maxlen=self.band_hist_len)
                          for k in self.band_names}

        # Buffer crudo (se crea en connect)
        self.buffer = None

        # ===== UI =====
        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Label(top, text="COM:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=22)
        self.port_cb["values"] = self._scan_ports()
        if self.port_cb["values"]: self.port_cb.current(0)
        else: self.port_var.set("COM3 / /dev/ttyACM0")
        self.port_cb.pack(side="left", padx=4)
        ttk.Button(top, text="↻", width=3,
                   command=lambda: self.port_cb.configure(values=self._scan_ports())
                   ).pack(side="left", padx=(0,8))

        ttk.Label(top, text="Baud:").pack(side="left")
        self.baud_var = tk.StringVar(value="115200")
        ttk.Entry(top, textvariable=self.baud_var, width=8).pack(side="left", padx=4)
        ttk.Button(top, text="Connect", command=self.connect).pack(side="left", padx=6)
        ttk.Button(top, text="Disconnect", command=self.disconnect).pack(side="left")

        ttk.Label(top, text="Fs (Hz):").pack(side="left", padx=(12,2))
        ttk.Entry(top, textvariable=self.fs, width=7).pack(side="left")
        ttk.Label(top, text="FFT window (s):").pack(side="left", padx=(12,2))
        ttk.Entry(top, textvariable=self.win_sec, width=7).pack(side="left")
        ttk.Label(top, text="Smooth N:").pack(side="left", padx=(12,2))
        ttk.Entry(top, textvariable=self.smooth_n, width=5).pack(side="left")
        ttk.Checkbutton(top, text="Remove DC", variable=self.rm_dc).pack(side="left", padx=(12,2))
        ttk.Checkbutton(top, text="Z-score view", variable=self.zscore_vis).pack(side="left", padx=(6,2))
        ttk.Checkbutton(top, text="Auto Y", variable=self.auto_y).pack(side="left", padx=(6,2))

        mid = ttk.LabelFrame(self, text="Band ranges (Hz) & Control", padding=8)
        mid.pack(fill="x", padx=8, pady=(6,2))

        # Rango por banda (labels con color usando tk.Label + fg)
        row1 = ttk.Frame(mid); row1.pack(fill="x")
        for name in self.band_names:
            lo_var, hi_var = self.band_vars[name]
            col = ttk.Frame(row1, padding=(2,0)); col.pack(side="left", padx=6)
            tk.Label(col, text=name, fg=BAND_COLORS[name]).pack()
            fr = ttk.Frame(col); fr.pack()
            ttk.Entry(fr, textvariable=lo_var, width=6).pack(side="left")
            ttk.Label(fr, text="–").pack(side="left")
            ttk.Entry(fr, textvariable=hi_var, width=6).pack(side="left")

        row2 = ttk.Frame(mid); row2.pack(fill="x", pady=(8,0))
        ttk.Label(row2, text="Control band:").pack(side="left")
        self.band_cb = ttk.Combobox(row2, values=self.band_names, textvariable=self.selected_band, width=8, state="readonly")
        self.band_cb.pack(side="left", padx=4)
        self.dir_cb = ttk.Combobox(row2, values=[">=", "<="], textvariable=self.direction, width=4, state="readonly")
        self.dir_cb.pack(side="left", padx=4)
        ttk.Label(row2, text="Threshold (0..1):").pack(side="left", padx=(6,2))
        ttk.Entry(row2, textvariable=self.threshold, width=6).pack(side="left")
        ttk.Checkbutton(row2, text="Enable control (send 1/0)", variable=self.enable_ctl).pack(side="left", padx=10)
        ttk.Checkbutton(row2, text="Lines instead of bars", variable=self.lines_mode).pack(side="left", padx=12)

        self.ctl_status = tk.StringVar(value="LED: (no control)")
        ttk.Label(row2, textvariable=self.ctl_status).pack(side="left", padx=12)

        # ===== Fig & Axes (GridSpec con 3 filas) =====
        fig = Figure(figsize=(13.2, 7.0), dpi=100)
        gs = GridSpec(3, 2, height_ratios=[3, 2, 2], figure=fig)

        # Fila 0: señal (todo el ancho)
        self.ax_time  = fig.add_subplot(gs[0, :])
        # Fila 1: PSD (todo el ancho para que respire)
        self.ax_psd   = fig.add_subplot(gs[1, :])
        # Fila 2: Band power (todo el ancho)
        self.ax_bands = fig.add_subplot(gs[2, :])

        # Ajuste de espaciado
        fig.subplots_adjust(left=0.07, right=0.98, top=0.95, bottom=0.07, wspace=0.25, hspace=0.45)

        # Traza temporal
        self.ax_time.set_title("EEG-like signal")
        self.ax_time.set_xlabel("samples (recent)")
        self.ax_time.set_ylabel("amplitude")
        self.time_line, = self.ax_time.plot([], [], lw=1, color=TIME_COLOR, label="Signal")
        self.ax_time.grid(True, alpha=0.3)

        # PSD
        self.ax_psd.set_title("PSD (last window)")
        self.ax_psd.set_xlabel("Hz")
        self.ax_psd.set_ylabel("Power")
        self.psd_line, = self.ax_psd.plot([], [], lw=1, color=PSD_COLOR, label="PSD")
        self.ax_psd.grid(True, alpha=0.3)

        # Band power (barras por defecto, luego se puede alternar a líneas)
        self.ax_bands.set_title("Band power (fraction of total)")
        self.ax_bands.set_ylim(0, 1.0)
        self.ax_bands.grid(True, alpha=0.25)

        # Barras iniciales bien espaciadas
        self.x_pos = np.arange(len(self.band_names))
        bar_colors = [BAND_COLORS[n] for n in self.band_names]
        self.bar_rects = self.ax_bands.bar(self.x_pos, [0]*len(self.band_names),
                                           width=0.65, color=bar_colors)
        self.ax_bands.set_xticks(self.x_pos)
        self.ax_bands.set_xticklabels(self.band_names, fontsize=10)
        self.ax_bands.set_xlim(-0.6, len(self.band_names)-0.4)
        self.ax_bands.margins(x=0.05)

        # Líneas de historial (ocultas por defecto)
        self.band_lines = {}
        for name in self.band_names:
            line, = self.ax_bands.plot([], [], lw=1.8, color=BAND_COLORS[name], label=name, alpha=0.95)
            line.set_visible(False)
            self.band_lines[name] = line
        self.ax_bands.legend(loc="upper right", fontsize=9)

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        # Loops
        self.after(40, self._tick_plot)
        self.after(120, self._tick_control)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----- Serial -----
    def _scan_ports(self):
        if not HAS_SERIAL: return []
        return [p.device for p in list_ports.comports()]

    def connect(self):
        if not HAS_SERIAL:
            messagebox.showerror("Serial", "Instala pyserial: pip install pyserial"); return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showinfo("Port", "Selecciona o escribe un COM."); return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror("Baud", "Baud inválido."); return

        fs = max(10.0, float(self.fs.get() or FS_DEFAULT))
        buf_len = int(BUFFER_SEC_DEFAULT * fs)
        buf_len = max(200, buf_len)
        self.buffer = deque([0.0]*buf_len, maxlen=buf_len)

        try:
            self.ser = serial.Serial(port, baudrate=baud, timeout=1)
            time.sleep(0.3)
        except Exception as e:
            messagebox.showerror("Connect", f"No se pudo abrir {port}:\n{e}")
            self.ser = None; return

        self.stop_event.clear()
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()
        self.connected = True
        self.last_sent = None

    def disconnect(self):
        self.stop_event.set()
        self.connected = False
        try:
            if self.ser and self.ser.is_open: self.ser.close()
        except Exception: pass
        self.ser = None

    def _reader(self):
        with self.ser:
            while not self.stop_event.is_set():
                try:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if not line: continue
                    val = float(line)
                    self.buffer.append(val)
                except ValueError:
                    continue
                except Exception:
                    break
        self.connected = False

    # ----- Procesamiento -----
    def _get_windowed_signal(self):
        if self.buffer is None or len(self.buffer) < 10:
            return None, None, None
        fs = max(10.0, float(self.fs.get() or FS_DEFAULT))
        win_sec = max(0.5, float(self.win_sec.get() or WIN_SEC_DEFAULT))
        N = int(round(fs * win_sec))
        if N < 32: N = 32
        if len(self.buffer) < N:
            return None, None, None

        x = np.array(list(self.buffer)[-N:], dtype=float)
        if self.rm_dc.get():
            x = x - np.mean(x)

        Nsmooth = max(1, int(self.smooth_n.get() or 1))
        if Nsmooth > 1 and N >= Nsmooth:
            cumsum = np.cumsum(np.insert(x, 0, 0.0))
            x = (cumsum[Nsmooth:] - cumsum[:-Nsmooth]) / float(Nsmooth)
            pad = np.full(N - x.size, x[0])
            x = np.concatenate([pad, x])

        x_vis = x.copy()
        if self.zscore_vis.get():
            std = np.std(x_vis)
            if std < 1e-9: std = 1.0
            x_vis = (x_vis - np.mean(x_vis)) / std
        return x, x_vis, fs

    def _compute_psd(self, x, fs):
        N = x.size
        if N < 32: return None, None
        w = np.hanning(N)
        X = np.fft.rfft(x * w, n=N)
        psd = (np.abs(X) ** 2) / (np.sum(w**2))
        freqs = np.fft.rfftfreq(N, d=1.0/fs)
        return freqs, psd

    def _band_power(self, freqs, psd, lo, hi):
        idx = np.where((freqs >= lo) & (freqs <= hi))[0]
        if idx.size == 0: return 0.0
        return float(np.sum(psd[idx]))

    # ----- Plot loop -----
    def _tick_plot(self):
        x, x_vis, fs = self._get_windowed_signal()
        if x is not None:
            # Señal temporal
            y = x_vis
            self.time_line.set_data(np.arange(y.size), y)
            self.ax_time.set_xlim(0, y.size-1)
            if self.auto_y.get():
                ymin, ymax = float(np.min(y)), float(np.max(y))
                if ymax <= ymin: ymax = ymin + 1.0
                span = ymax - ymin; pad = max(0.5, span*0.15)
                self.ax_time.set_ylim(ymin - pad, ymax + pad)

            # PSD + bandas
            freqs, psd = self._compute_psd(x, fs)
            if freqs is not None:
                self.psd_line.set_data(freqs, psd)
                self.ax_psd.set_xlim(0, max(50.0, float(np.max(freqs))))
                if np.max(psd) > 0: self.ax_psd.set_ylim(0, float(np.max(psd))*1.1)

                total_lo, total_hi = TOTAL_BAND
                p_total = self._band_power(freqs, psd, total_lo, total_hi)
                bars = []
                for name in self.band_names:
                    lo = float(self.band_vars[name][0].get())
                    hi = float(self.band_vars[name][1].get())
                    if lo > hi: lo, hi = hi, lo
                    p = self._band_power(freqs, psd, lo, hi)
                    frac = (p / p_total) if p_total > 1e-12 else 0.0
                    bars.append(frac)
                    # actualizar historial para líneas
                    self.band_hist[name].append(frac)

                # Toggle barras vs líneas
                show_lines = self.lines_mode.get()
                if show_lines:
                    # Oculta barras
                    for rect in self.bar_rects:
                        rect.set_visible(False)
                    # Muestra líneas con historial y ajusta ejes
                    x_hist = np.arange(self.band_hist_len)
                    for name in self.band_names:
                        y_hist = list(self.band_hist[name])
                        line = self.band_lines[name]
                        line.set_data(x_hist, y_hist)
                        line.set_visible(True)
                    self.ax_bands.set_xlim(0, self.band_hist_len-1)
                    self.ax_bands.set_ylim(0, 1.0)
                else:
                    # Muestra barras y actualiza alturas + ejes
                    for rect, v in zip(self.bar_rects, bars):
                        rect.set_height(v)
                        rect.set_visible(True)
                    for name in self.band_names:
                        self.band_lines[name].set_visible(False)
                    self.ax_bands.set_xticks(self.x_pos)
                    self.ax_bands.set_xticklabels(self.band_names, fontsize=10)
                    self.ax_bands.set_xlim(-0.6, len(self.band_names)-0.4)
                    self.ax_bands.set_ylim(0, 1.0)
                    self.ax_bands.margins(x=0.05)

        self.canvas.draw_idle()
        self.after(40, self._tick_plot)

    # ----- Control LED -----
    def _tick_control(self):
        if self.enable_ctl.get() and self.connected and self.ser is not None:
            x, _, fs = self._get_windowed_signal()
            if x is not None:
                freqs, psd = self._compute_psd(x, fs)
                if freqs is not None:
                    band = self.selected_band.get()
                    try:
                        lo = float(self.band_vars[band][0].get())
                        hi = float(self.band_vars[band][1].get())
                        if lo > hi: lo, hi = hi, lo
                    except Exception:
                        lo, hi = BANDS_DEFAULT.get(band, (8.0, 12.0))
                    total_lo, total_hi = TOTAL_BAND
                    p_total = self._band_power(freqs, psd, total_lo, total_hi)
                    p_band  = self._band_power(freqs, psd, lo, hi)
                    frac = (p_band / p_total) if p_total > 1e-12 else 0.0

                    thr = float(self.threshold.get() or 0.3)
                    cond = (frac >= thr) if self.direction.get() == ">=" else (frac <= thr)
                    want = '1' if cond else '0'
                    if want != self.last_sent:
                        try:
                            self.ser.write(want.encode())
                            self.last_sent = want
                            self.ctl_status.set(f"LED: {'ON' if want=='1' else 'OFF'} | {band}={frac:.2f} (thr {self.direction.get()} {thr:.2f})")
                        except Exception:
                            pass
        self.after(120, self._tick_control)

    # ----- Cierre -----
    def on_close(self):
        self.disconnect()
        self.destroy()

if __name__ == "__main__":
    EEGBandControl().mainloop()
