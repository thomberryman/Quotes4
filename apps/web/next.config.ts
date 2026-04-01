import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typedRoutes: false,
  transpilePackages: ["@quotes4/contracts", "@quotes4/domain"]
};

export default nextConfig;
