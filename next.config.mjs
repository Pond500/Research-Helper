/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const agentBase = process.env.REMOTE_ACTION_URL || 'http://localhost:10236/copilotkit';
    const agentInternal = process.env.AGENT_INTERNAL_URL || 'http://localhost:10236';
    return [
      {
        source: '/charts/:path*',
        destination: `${agentInternal}/charts/:path*`,
      },
      {
        source: '/api/upload',
        destination: `${agentInternal}/upload`,
      },
      {
        source: '/api/agent/:path*',
        destination: `${agentBase}/agents/:path*`,
      },
    ]
  }
};

export default nextConfig;
