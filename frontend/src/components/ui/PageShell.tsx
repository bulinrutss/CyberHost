import { Navbar } from "@/components/Navbar";

type Props = {
  children: React.ReactNode;
  admin?: boolean;
  wide?: boolean;
};

export function PageShell({ children, admin, wide }: Props) {
  return (
    <div className="page-bg">
      <Navbar admin={admin} />
      <main
        className={`relative z-10 mx-auto px-4 sm:px-6 py-10 sm:py-14 ${
          wide ? "max-w-cyber" : "max-w-6xl"
        }`}
      >
        {children}
      </main>
    </div>
  );
}
