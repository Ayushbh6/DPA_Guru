import LoginForm from "@/components/LoginForm";


export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const params = await searchParams;
  const nextPath = typeof params.next === "string" && params.next.startsWith("/") ? params.next : "/";

  return (
    <main
      className="flex min-h-screen items-center justify-center px-6 py-16"
      style={{ background: "var(--bg)", color: "var(--text)" }}
    >
      <LoginForm nextPath={nextPath} />
    </main>
  );
}
