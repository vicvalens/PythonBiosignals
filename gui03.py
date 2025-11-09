import matplotlib.pyplot as plt

# FIguras y ejes
fig, ax = plt.subplots(figsize=(8, 4))

# Opcional: define límites (solo para mostrar el marco de una futura señal)
ax.set_xlim(0, 500)     # 500 muestras hipotéticas
ax.set_ylim(0, 1023)    # rango típico de 10 bits (ajustable)
ax.set_title("Señal biosensor (placeholder)")
ax.set_xlabel("muestras")
ax.set_ylabel("amplitud")
ax.grid(True, alpha=0.3)

# Mensaje centrado
ax.text(
    0.5, 0.5,
    "Esperando señal…",
    ha="center", va="center",
    transform=ax.transAxes,
    fontsize=14
)

plt.tight_layout()
plt.show()