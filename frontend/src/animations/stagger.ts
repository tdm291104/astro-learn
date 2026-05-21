import type { Variants } from "framer-motion";

export const staggerContainer: Variants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.08 } },
};

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};
