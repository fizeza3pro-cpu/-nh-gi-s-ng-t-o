import { memo, useEffect, useRef } from "react";
import Lottie, { type LottieRefCurrentProps } from "lottie-react";

import animationData from "@/assets/ai-thinking-loader.json";
import { usePrefersReducedMotion } from "@/hooks/use-prefers-reduced-motion";

const RENDERER_SETTINGS = {
  preserveAspectRatio: "xMidYMid meet",
  progressiveLoad: true,
  hideOnTransparent: true,
} as const;

function AiThinkingAnimation() {
  const reducedMotion = usePrefersReducedMotion();
  const lottieRef = useRef<LottieRefCurrentProps>(null);

  useEffect(() => {
    const syncPlayback = () => {
      lottieRef.current?.setSubframe(false);
      if (reducedMotion) {
        lottieRef.current?.goToAndStop(42, true);
      } else if (document.hidden) {
        lottieRef.current?.pause();
      } else {
        lottieRef.current?.setSpeed(0.8);
        lottieRef.current?.play();
      }
    };

    syncPlayback();
    document.addEventListener("visibilitychange", syncPlayback);
    return () => document.removeEventListener("visibilitychange", syncPlayback);
  }, [reducedMotion]);

  return (
    <div className="mx-auto h-36 w-36 [contain:layout_paint]" aria-hidden="true">
      <Lottie
        lottieRef={lottieRef}
        animationData={animationData}
        autoplay={!reducedMotion}
        loop={!reducedMotion}
        className="h-full w-full"
        rendererSettings={RENDERER_SETTINGS}
      />
    </div>
  );
}

export default memo(AiThinkingAnimation);
