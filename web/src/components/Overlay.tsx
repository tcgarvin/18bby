import type { ReactNode } from "react";

interface OverlayProps {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

/** A large panel over the current view, for the game log. Esc or the backdrop closes it. */
export function Overlay({ title, onClose, children }: OverlayProps) {
  return (
    <div
      className="overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="overlay__panel" role="dialog" aria-modal="true">
        <header className="overlay__head">
          <h2 className="overlay__title">{title}</h2>
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
