/** Framer Motion presets — consistent timing across the app */

export const easeSoft   = [0.25, 0.1, 0.25, 1];
export const easeSpring = { type: "spring", stiffness: 280, damping: 24 };
export const easeBounce = { type: "spring", stiffness: 400, damping: 18 };

export const subtle = { duration: 0.32, ease: easeSoft };

export const fadeIn = {
  initial:    { opacity: 0 },
  animate:    { opacity: 1 },
  transition: subtle,
};

export const fadeInProps = fadeIn;   // alias for legacy imports

export const slideUp = {
  initial:    { opacity: 0, y: 16 },
  animate:    { opacity: 1, y: 0  },
  transition: subtle,
};

export const slideUpProps = slideUp; // alias

export const slideRight = {
  initial:    { opacity: 0, x: -14 },
  animate:    { opacity: 1, x: 0   },
  transition: subtle,
};

export const scaleIn = {
  initial:    { opacity: 0, scale: 0.92 },
  animate:    { opacity: 1, scale: 1    },
  transition: { duration: 0.35, ease: easeSoft },
};

export const buttonHoverProps = {
  whileHover:  { scale: 1.025 },
  whileTap:    { scale: 0.975 },
  transition:  { duration: 0.18, ease: easeSoft },
};

/** Stagger container — wrap children with this */
export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.07, delayChildren: 0.05 } },
};

/** Each staggered child uses this */
export const staggerChild = {
  initial:    { opacity: 0, y: 18 },
  animate:    { opacity: 1, y: 0  },
  transition: { duration: 0.38, ease: easeSoft },
};
