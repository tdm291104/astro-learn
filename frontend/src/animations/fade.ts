import type { Transition, Variants } from "framer-motion";

export const fadeIn: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

export const fadeInUp: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
};

export const fadeOut: Variants = {
  initial: { opacity: 1 },
  animate: { opacity: 0 },
};

export const fadeTransition: Transition = { duration: 0.3, ease: "easeOut" };
