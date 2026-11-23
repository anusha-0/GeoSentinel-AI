import type { HTMLAttributes } from "react";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "calcite-chip": HTMLAttributes<HTMLElement> & {
        kind?: string;
        scale?: string;
      };
      "calcite-icon": HTMLAttributes<HTMLElement> & {
        icon?: string;
        scale?: string;
      };
      "calcite-button": HTMLAttributes<HTMLElement> & {
        appearance?: string;
        kind?: string;
        width?: string;
        disabled?: boolean;
        type?: "button" | "submit" | "reset";
      };
      "calcite-notice": HTMLAttributes<HTMLElement> & {
        open?: boolean;
        kind?: string;
        scale?: string;
      };
    }
  }
}
