interface StatCardProps {
  title: string;
  value: string;
  description: string;
}

export function StatCard({ title, value, description }: StatCardProps) {
  return (
    <article className="card">
      <h3>{title}</h3>
      <strong>{value}</strong>
      <p>{description}</p>
    </article>
  );
}

