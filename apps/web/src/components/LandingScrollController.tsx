"use client";

import { useEffect, useRef } from "react";

const SCROLL_LOCK_MS = 820;
const WHEEL_THRESHOLD = 18;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function getTargetY(element: HTMLElement) {
  const rect = element.getBoundingClientRect();
  const currentY = window.scrollY;
  const maxY = document.documentElement.scrollHeight - window.innerHeight;

  if (element.dataset.landingSnap === "start") {
    return clamp(element.offsetTop, 0, maxY);
  }

  return clamp(currentY + rect.top + rect.height / 2 - window.innerHeight / 2, 0, maxY);
}

export default function LandingScrollController() {
  const lockedRef = useRef(false);
  const unlockTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const previousSnapType = document.documentElement.style.scrollSnapType;
    const previousScrollPaddingTop = document.documentElement.style.scrollPaddingTop;

    document.documentElement.style.scrollSnapType = "none";
    document.documentElement.style.scrollPaddingTop = "0px";

    const unlock = () => {
      lockedRef.current = false;
      if (unlockTimerRef.current) {
        window.clearTimeout(unlockTimerRef.current);
        unlockTimerRef.current = null;
      }
    };

    const getStops = () => {
      return Array.from(document.querySelectorAll<HTMLElement>("[data-landing-snap]"))
        .map((element) => ({ element, y: getTargetY(element) }))
        .sort((a, b) => a.y - b.y);
    };

    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) < WHEEL_THRESHOLD) return;
      if ((event.target as HTMLElement | null)?.closest("[data-scroll-free]")) return;

      const stops = getStops();
      if (stops.length < 2) return;

      event.preventDefault();
      if (lockedRef.current) return;

      const currentY = window.scrollY;
      const direction = event.deltaY > 0 ? 1 : -1;
      const currentIndex = stops.reduce((closestIndex, stop, index) => {
        const closestDistance = Math.abs(stops[closestIndex].y - currentY);
        const distance = Math.abs(stop.y - currentY);
        return distance < closestDistance ? index : closestIndex;
      }, 0);
      const nextIndex = clamp(currentIndex + direction, 0, stops.length - 1);
      const nextY = stops[nextIndex].y;

      lockedRef.current = true;
      window.scrollTo({ top: nextY, behavior: "smooth" });
      unlockTimerRef.current = window.setTimeout(unlock, SCROLL_LOCK_MS);
    };

    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("resize", unlock);

    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("resize", unlock);
      document.documentElement.style.scrollSnapType = previousSnapType;
      document.documentElement.style.scrollPaddingTop = previousScrollPaddingTop;
      unlock();
    };
  }, []);

  return null;
}
