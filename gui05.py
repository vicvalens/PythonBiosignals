import math, random, time
import tkinter as tk
from tkinter import ttk
from collections import deque
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Parámetros base
BUFFER_LEN  = 400     # muestras visibles
INTERVAL_MS = 40      # ~25 Hz
Y_RANGE     = 1023    # eje Y: [-Y_RANGE, +Y_RANGE]

class SimBioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulador de biosensor")
        self.geometry("880x520")

        # Estado de simulación
        self.buffer = deque([0]*BUFFER_LEN, maxlen=BUFFER_LEN)
        self.running = False
        self.t = 0.0
        self.dt = INTERVAL_MS / 1000.0

        # ----- Controles -----
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Amplitud (±):").pack(side="left")
        self.amp_var = tk.DoubleVar(value=400.0)
        ttk.Entry(top, textvariable=self.amp_var, width=8).pack(side="left", padx=5)

        ttk.Label(top, text="Frecuencia (Hz):").pack(side="left", padx=(10,0))
        self.freq_var = tk.DoubleVar(value=0.8)
        ttk.Entry(top, textvariable=self.freq_var, width=8).pack(side="left", padx=5)

        ttk.Label(top, text="Ruido (0–100):").pack(side="left", padx=(10,0))
        self.noise_var = tk.DoubleVar(value=8.0)
        ttk.Entry(top, textvariable=self.noise_var, width=8).pack(side="left", padx=5)

        ttk.Button(top, text="Iniciar", command=self.start).pack(side="left", padx=(12,4))
        ttk.Button(top, text="Detener", command=self.stop).pack(side="left")
        ttk.Button(top, text="Limpiar", command=self.clear).pack(side="left", padx=6)

        ttk.Label(top, text="Señal = A·sin(2πft) + ruido. Eje centrado en 0.").pack(side="left", padx=16)

        # ----- Gráfica -----
        fig = Figure(figsize=(8.2, 3.6), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("Biosensor simulado (tiempo real)")
        self.ax.set_xlabel("muestras")
        self.ax.set_ylabel("amplitud")
        self.ax.set_xlim(0, BUFFER_LEN-1)
        self.ax.set_ylim(-Y_RANGE, Y_RANGE)
        self.ax.grid(True, alpha=0.3)
        self.ax.axhline(0, lw=1, alpha=0.6)
        (self.line,) = self.ax.plot(range(BUFFER_LEN), list(self.buffer), lw=1)

        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Cierre limpio
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- Simulador ----------------
    def sample(self):
        A = max(0.0, min(Y_RANGE, float(self.amp_var.get())))
        f = max(0.0, float(self.freq_var.get()))
        n = max(0.0, float(self.noise_var.get()))
        # seno centrado en 0
        s = A * math.sin(2*math.pi*f*self.t)
        # ruido uniforme acotado
        r = random.uniform(-n, n)
        self.t += self.dt
        return s + r

    def tick(self):
        if not self.running:
            return
        y = self.sample()
        # recorte seguro al rango
        y = max(-Y_RANGE, min(Y_RANGE, y))
        self.buffer.append(y)
        self.line.set_ydata(self.buffer)
        self.canvas.draw_idle()
        self.after(INTERVAL_MS, self.tick)

    # -------------- Controles --------------
    def start(self):
        if self.running:
            return
        self.running = True
        self.tick()

    def stop(self):
        self.running = False

    def clear(self):
        self.buffer.clear()
        for _ in range(BUFFER_LEN):
            self.buffer.append(0)
        self.line.set_ydata(self.buffer)
        self.canvas.draw_idle()

    def on_close(self):
        self.running = False
        self.destroy()

if __name__ == "__main__":
    SimBioApp().mainloop()
