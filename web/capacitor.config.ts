import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.collabai.app',
  appName: '叮叮',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
  },
};

export default config;
