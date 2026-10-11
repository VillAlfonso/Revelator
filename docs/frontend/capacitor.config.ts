import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.forgeguard.app',
  appName: 'Revelator',
  webDir: 'dist',
  backgroundColor: '#000000',
  android: {
    allowMixedContent: true,
    backgroundColor: '#000000',
    webContentsDebuggingEnabled: true,
  },
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
  plugins: {
    GoogleAuth: {
      scopes: ['profile', 'email'],
      serverClientId: '676322212303-52bprvcqb4dao6c71m3500lqh2i9i6mb.apps.googleusercontent.com',
      forceCodeForRefreshToken: true,
    },
    Camera: {
      permissions: ['camera', 'photos'],
    },
    SplashScreen: {
      launchShowDuration: 1200,
      backgroundColor: '#000000',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER',
      showSpinner: false,
    },
  },
};

export default config;
