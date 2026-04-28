interface StatCardProps {
  label: string;
  value: string | number;
  sub?:  string;
  color?: "indigo" | "green" | "yellow" | "red" | "blue" | "purple";
  icon?:  string;
}

const colors = {
  indigo:  "border-indigo-500/30  bg-indigo-500/5",
  green:   "border-green-500/30   bg-green-500/5",
  yellow:  "border-yellow-500/30  bg-yellow-500/5",
  red:     "border-red-500/30     bg-red-500/5",
  blue:    "border-blue-500/30    bg-blue-500/5",
  purple:  "border-purple-500/30  bg-purple-500/5",
};

const textColors = {
  indigo:  "text-indigo-400",
  green:   "text-green-400",
  yellow:  "text-yellow-400",
  red:     "text-red-400",
  blue:    "text-blue-400",
  purple:  "text-purple-400",
};

export function StatCard({ label, value, sub, color = "indigo", icon }: StatCardProps) {
  return (
    <div className={`rounded-xl border p-5 ${colors[color]}`}>
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${textColors[color]}`}>
        {icon && <span className="mr-1">{icon}</span>}{value}
      </p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}
