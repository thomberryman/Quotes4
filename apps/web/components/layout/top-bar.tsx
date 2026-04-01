import { LogoutButton } from "./logout-button";

export function TopBar({
  userName,
  userEmail,
  onOpenNav
}: {
  userName: string;
  userEmail: string;
  onOpenNav?: () => void;
}) {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur lg:px-6">
      <div className="flex items-center gap-3">
        {onOpenNav ? (
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 text-slate-700 lg:hidden"
            onClick={onOpenNav}
            type="button"
          >
            Menu
          </button>
        ) : null}
        <div>
          <p className="text-sm font-semibold text-slate-900">Quotes4</p>
          <p className="text-xs text-slate-500">Operational quoting and forecasting workspace</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="hidden text-right sm:block">
          <p className="text-sm font-medium text-slate-900">{userName}</p>
          <p className="text-xs text-slate-500">{userEmail}</p>
        </div>
        <LogoutButton />
      </div>
    </header>
  );
}
