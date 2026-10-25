import { useAnimatedNumber } from "./useAnimatedNumber";

/** A number that ticks toward each new value (cash, treasury, price) instead of jumping. */
export function Ticker({ value, durationMs = 500 }: { value: number; durationMs?: number }) {
  const shown = useAnimatedNumber(value, durationMs);
  return <>{shown}</>;
}
