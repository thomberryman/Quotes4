export function ErrorState({
  title,
  description
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-5 py-4">
      <h3 className="text-sm font-semibold text-rose-900">{title}</h3>
      <p className="mt-1 text-sm text-rose-800">{description}</p>
    </div>
  );
}
