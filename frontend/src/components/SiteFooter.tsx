export default function SiteFooter() {
  return (
    <footer className="border-t border-border/80 bg-background">
      <div className="container flex flex-col gap-3 py-8 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <p>Bản thử nghiệm</p>
        <p className="text-xs">Tách ý → đối chiếu mã → chấm điểm</p>
      </div>
    </footer>
  );
}
