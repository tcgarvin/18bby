import type { ReactNode } from "react";

interface OverlayProps {
  title: ReactNode;
  /** Extra header content, e.g. the map's corporation focus buttons. */
  tools?: ReactNode;
  wide?: boolean;
  /** Size the panel to its content instead of a fixed height. */
  fit?: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** A large panel over the current view, for the map, market or log. Esc or the backdrop closes it. */
export function Overlay({ title, tools, wide = false, fit = false, onClose, children }: OverlayProps) {
  return (
    <div
      className="overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className={`overlay__panel${wide ? " overlay__panel--wide" : ""}${fit ? " overlay__panel--fit" : ""}`} role="dialog" aria-modal="true">
        <header className="overlay__head">
          <h2 className="overlay__title">{title}</h2>
          {tools}
          <button type="button" className="btn btn--small overlay__close" onClick={onClose}>
            <span>
              Close <kbd>Esc</kbd>
            </span>
          </button>
        </header>
        <div className="overlay__body">{children}</div>
      </section>
    </div>
  );
}
