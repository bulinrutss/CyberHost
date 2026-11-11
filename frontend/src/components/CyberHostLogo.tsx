import { publicAsset } from "@/lib/publicAsset";
import Image from "next/image";
import Link from "next/link";

type Props = {
  href?: string;
  className?: string;
  height?: number;
};

export function CyberHostLogo({ href = "/", className = "", height = 48 }: Props) {
  const img = (
    <Image
      src={publicAsset("/logo2.png")}
      alt="CyberHost"
      width={1089}
      height={237}
      className={`block object-contain shrink-0 ${className}`}
      style={{ height, width: "auto", maxHeight: height }}
      priority
    />
  );

  if (!href) return img;
  return (
    <Link href={href} className="inline-flex items-center shrink-0 hover:opacity-90 transition-opacity">
      {img}
    </Link>
  );
}
