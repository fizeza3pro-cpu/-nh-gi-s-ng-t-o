export default function SiteFooter() {
  return (
    <footer className="border-t border-border/80 bg-background">
      <div className="container flex flex-col gap-3 py-8 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>Bản DEMO</p>
        <p className="font-mono text-xs">Pipeline Mapping → Scoring</p>
      </div>
    </footer>
  );
}
