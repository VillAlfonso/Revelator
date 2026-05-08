import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.forgeguard.app',
  appName: 'Revelator',
  webDir: 'dist',
  backgroundColor: '#000000',
  server: {
    // For development: point to your backend API
    // For production: remove this and bundle the frontend
    // url: 'http://10.0.2.2:8000',  // Android emulator → host machine
    androidScheme: 'https',
  },
  plugins: {
    Camera: {
      // Camera permissions for document scanning
    },
    SplashScreen: {
      backgroundColor: '#000000',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER',
      showSpinner: false,
    },
  },
  android: {
    // Allow mixed content for dev (HTTP API calls)
    allowMixedContent: true,
    backgroundColor: '#000000',
  },
};

export default config;
