import type { CSSProperties } from "react";
import { useRules } from "../help/rulesContext";
import "./CertStack.css";

export type CertSize = "sm" | "md";

/** Certificates drawn behind the top one, at most; a bigger pile shows its size in the count. */
const MAX_LAYERS: Record<CertSize, number> = { sm: 3, md: 4 };

interface CertStackProps {
  corpId: string;
  color: string;
  /** Shares in the pile (the president's certificate counts as several). */
  shares: number;
  /** The pile includes the president's certificate, drawn on top. */
  president?: boolean;
  size?: CertSize;
  /** Show the share count beside the pile. */
  showCount?: boolean;
  title?: string;
}

/**
 * A small pile of share certificates in the corporation's colour, with the share count beside
 * it. The president's certificate is wider and gold-framed; an empty pile is a dashed outline.
 */
export function CertStack({ corpId, color, shares, president = false, size = "sm", showCount = true, title }: CertStackProps) {
  const rules = useRules();
  const certificates = certificateCount(shares, president, rules.presidentShareSize);
  const layers = Math.max(0, Math.min(certificates - 1, MAX_LAYERS[size]));
  const style = { ["--corp" as string]: color, ["--layers" as string]: layers } as CSSProperties;
  return (
    <span
      className={`cert cert--${size}${shares === 0 ? " cert--empty" : ""}`}
      style={style}
      title={title ?? describe(corpId, shares, president)}
    >
      <span className="cert__pile" aria-hidden="true">
        {Array.from({ length: layers }, (_, i) => (
          <span key={i} className="cert__layer" style={{ ["--i" as string]: layers - i }} />
        ))}
        <span className={`cert__card${president ? " cert__card--president" : ""}`}>
          {president && <span className="cert__star">★</span>}
          {corpId}
        </span>
      </span>
      {showCount && <span className="cert__count num">{shares}</span>}
    </span>
  );
}

/** How many certificates hold `shares` shares, when one of them may be the president's. */
export function certificateCount(shares: number, president: boolean, presidentShareSize: number): number {
  if (shares <= 0) return 0;
  return president ? 1 + Math.max(0, shares - presidentShareSize) : shares;
}

function describe(corpId: string, shares: number, president: boolean): string {
  const noun = shares === 1 ? "share" : "shares";
  return `${shares} ${corpId} ${noun}${president ? ", including the president's certificate" : ""}`;
}
