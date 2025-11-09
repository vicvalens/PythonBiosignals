import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

BUFFER_LEN  = 300       # muestras visibles
INTERVAL_MS = 40        # ~25 Hz (cada tick)
Y_RANGE     = 1023      # eje: [-Y_RANGE, +Y_RANGE]

class PulseWidthApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Pulso con duración")
        self.geometry("820x500")

        # Estado
        self.buffer = deque([0]*BUFFER_LEN, maxlen=BUFFER_LEN)
        self.running = True
        self.pulse_value = 0.0
        self.pulse_ticks_left = 0   # cuántos ticks quedan del pulso

        # UI superior
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Valor (±):").pack(side="left")
        self.val_var = tk.StringVar(value="300")
        ttk.Entry(top, textvariable=self.val_var, width=8).pack(side="left", padx=5)

        ttk.Label(top, text="Duración (ms):").pack(side="left", padx=(10,0))
        self.ms_var = tk.StringVar(value="200")
        ttk.Entry(top, textvariable=self.ms_var, width=8).pack(side="left", padx=5)

        ttk.Button(top, text="Pulso", command=self.trigger_pulse).pack(side="left", padx=(10,5))
        ttk.Button(top, text="Limpiar", command=self.clear_line).pack(side="left")

        ttk.Label(top, text="Base 0 centrada; el pulso mantiene el valor N ms y luego vuelve a 0.").pack(side="left", padx=12)

        # Figura / gráfica
        fig = Figure(figsize=(7.6, 3.6), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("Señal + pulso con duración")
        self.ax.set_xlabel("muestras")
        self.ax.set_ylabel("amplitud")
        self.ax.set_xlim(0, BUFFER_LEN-1)
        self.ax.set_ylim(-Y_RANGE, Y_RANGE)
        self.ax.grid(True, alpha=0.3)
        self.ax.axhline(0, lw=1, alpha=0.6)

        (self.line,) = self.ax.plot(range(BUFFER_LEN), list(self.buffer), lw=1)
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Loop de actualización
        self.after(INTERVAL_MS, self._tick)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def trigger_pulse(self):
        # Leer valor y duración
        try:
            val = float(self.val_var.get().strip())
        except ValueError:
            messagebox.showerror("Valor inválido", f"No es numérico: {self.val_var.get()}")
            return
        try:
            dur_ms = int(float(self.ms_var.get().strip()))
        except ValueError:
            messagebox.showerror("Duración inválida", f"No es numérica: {self.ms_var.get()}")
            return

        # Limitar al rango visible y a una duración mínima de un tick
        val = max(-Y_RANGE, min(Y_RANGE, val))
        ticks = max(1, int(round(dur_ms / INTERVAL_MS)))

        self.pulse_value = val
        self.pulse_ticks_left = ticks

    def clear_line(self):
        self.buffer.clear()
        for _ in range(BUFFER_LEN):
            self.buffer.append(0)
        self.line.set_ydata(self.buffer)
        self.canvas.draw_idle()

    def _tick(self):
        # Si queda pulso, usarlo; si no, 0
        if self.pulse_ticks_left > 0:
            sample = self.pulse_value
            self.pulse_ticks_left -= 1
        else:
            sample = 0.0

        self.buffer.append(sample)
        self.line.set_ydata(self.buffer)
        self.canvas.draw_idle()

        if self.running:
            self.after(INTERVAL_MS, self._tick)

    def on_close(self):
        self.running = False
        self.destroy()

if __name__ == "__main__":
    PulseWidthApp().mainloop()
