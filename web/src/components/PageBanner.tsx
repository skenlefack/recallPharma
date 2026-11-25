import { Wave } from "@/components/Wave";
import { IMAGES } from "@/lib/images";

/** Bandeau des pages intérieures : image de fond, titre centré, bord ondulé. */
export function PageBanner({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: React.ReactNode }) {
  return (
    <section className="page-banner full-bleed" style={{ backgroundImage: `url(${IMAGES.bandeau})` }}>
      <div className="page-banner-inner">
        {eyebrow && <div className="kicker">{eyebrow}</div>}
        <h1>{title}</h1>
        {children && <p>{children}</p>}
      </div>
      <Wave />
    </section>
  );
}
