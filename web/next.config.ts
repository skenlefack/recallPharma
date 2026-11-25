import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // image Docker : serveur autonome, sans node_modules complet
};

export default nextConfig;
