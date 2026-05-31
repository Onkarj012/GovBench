import Link from "next/link";

const NAV = [
  { href: "/blog",         label: "Blog"        },
  { href: "/methodology",  label: "Methodology" },
  { href: "/docs",         label: "Docs"        },
  { href: "/data",         label: "Data"        },
  { href: "https://github.com/onkarj012/irbg", label: "GitHub", external: true },
];

export default function Nav({ active }: { active?: string }) {
  return (
    <header className="sticky top-0 z-10 h-14 border-b border-border bg-background flex items-center px-4">
      <Link href="/"
        className="text-[20px] font-semibold tracking-[-0.02em] leading-none text-foreground mr-6">
        GovBench
      </Link>
      <nav className="flex items-center flex-1 gap-1">
        {NAV.map(({ href, label, external }) => (
          <a key={href} href={href}
            target={external ? "_blank" : undefined}
            rel={external ? "noopener noreferrer" : undefined}
            className={`px-3 h-9 inline-flex items-center text-sm transition-colors
              ${active === label
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"}`}>
            {label}
          </a>
        ))}
      </nav>
    </header>
  );
}
