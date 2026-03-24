import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.collabai.app',
  appName: 'CollabAI',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
  },
};

export default config;
