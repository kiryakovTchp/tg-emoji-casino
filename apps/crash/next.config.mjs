/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
  experimental: {
    allowedDevOrigins: ['https://46c6-45-144-52-194.ngrok-free.app'],
  },
  output: "standalone",
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: http: data: blob: ws: wss:",
              "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com data:",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "img-src 'self' data: https: blob:",
              "connect-src 'self' https: http: ws: wss: data: blob:"
            ].join('; ')
          }
        ]
      }
    ]
  }
}

export default nextConfig
