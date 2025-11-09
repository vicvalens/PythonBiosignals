import matplotlib.pyplot as plt

fig, ax = plt.subplots()
ax.set_title("Señal biosensor")
ax.text(0.5, 0.5, "Esperando señal…", ha="center", va="center", transform=ax.transAxes)
plt.show()