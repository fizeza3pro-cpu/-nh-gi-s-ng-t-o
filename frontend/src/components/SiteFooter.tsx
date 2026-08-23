export default function SiteFooter() {
  return (
    <footer className="border-t border-border/80 bg-background">
      <div className="container flex flex-col gap-3 py-8 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>
          AUT tiếng Việt ·{" "}
          <em className="font-serif">Đề tài nghiên cứu demo</em>, Học viện Kỹ
          thuật Quân sự 2026.
        </p>
        <p className="font-mono text-xs">
          Pipeline 2 tầng{" "}
          <span className="text-foreground">Mapping → Scoring</span>
        </p>
      </div>
    </footer>
  );
}
