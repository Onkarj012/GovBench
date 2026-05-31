import Link from "next/link";

const NAV = [
  { href: "/blog", label: "Blog" },
  { href: "/methodology", label: "Methodology" },
  { href: "/docs", label: "Docs" },
  { href: "/data", label: "Data" },
];

const GITHUB = "https://github.com/Onkarj012/GovBench";

export default function Nav({ active }: { active?: string }) {
  return (
    <header className="sticky top-0 z-10 h-14 border-b border-border bg-background/80 backdrop-blur flex items-center px-4">
      <Link
        href="/"
        className="text-[20px] font-semibold tracking-[-0.02em] leading-none text-foreground mr-6"
      >
        GovBench
      </Link>
      <nav className="flex items-center flex-1 gap-1">
        {NAV.map(({ href, label }) => {
          const isActive = active === label;
          return (
            <Link
              key={href}
              href={href}
              aria-current={isActive ? "page" : undefined}
              className={`relative px-3 h-14 inline-flex items-center text-sm transition-colors ${
                isActive
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {label}
              {isActive && (
                <span className="absolute bottom-0 left-3 right-3 h-px bg-foreground" />
              )}
            </Link>
          );
        })}
      </nav>
      <a
        href={GITHUB}
        target="_blank"
        rel="noopener noreferrer"
        className="px-3 h-9 inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        GitHub ↗
      </a>
    </header>
  );
}
