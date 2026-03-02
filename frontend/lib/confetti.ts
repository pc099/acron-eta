import confetti from "canvas-confetti";

/**
 * Fire confetti with ASAHI brand colours.
 */
export function fireConfetti() {
  const colors = ["#FF6B35", "#FFB84D", "#FFF3E0"];
  const defaults = {
    origin: { y: 0.7 },
    colors,
    zIndex: 9999,
  };

  confetti({
    ...defaults,
    particleCount: 80,
    spread: 60,
    startVelocity: 40,
  });

  setTimeout(() => {
    confetti({
      ...defaults,
      particleCount: 50,
      spread: 90,
      startVelocity: 30,
      origin: { x: 0.3, y: 0.6 },
    });
  }, 200);

  setTimeout(() => {
    confetti({
      ...defaults,
      particleCount: 50,
      spread: 90,
      startVelocity: 30,
      origin: { x: 0.7, y: 0.6 },
    });
  }, 400);
}
