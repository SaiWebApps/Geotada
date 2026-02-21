# Next Steps - Setting Up the React Native Mobile App

## Prerequisites

Before proceeding, you need to install Node.js and npm:

### Install Node.js (macOS)

Choose one of these methods:

**Option 1: Using Homebrew (Recommended)**
```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Node.js LTS version
brew install node@20

# Verify installation
node --version  # Should show v20.x.x
npm --version   # Should show v10.x.x
```

**Option 2: Download from nodejs.org**
1. Visit https://nodejs.org/
2. Download the LTS version (recommended)
3. Run the installer
4. Verify: `node --version && npm --version`

## Step 1: Create the Mobile App

Once Node.js is installed:

```bash
# Navigate to project root
cd /Users/adamserblowski/Geotada

# Create React Native app with Expo
npx create-expo-app mobile --template blank-typescript

# Navigate to mobile directory
cd mobile

# Install required dependencies
npm install axios
npm install @react-navigation/native @react-navigation/stack
npm install react-native-screens react-native-safe-area-context
npm install @react-native-async-storage/async-storage
```

## Step 2: Project Structure

Create the following structure:

```
mobile/
├── App.tsx                 # Main app component
├── app.json               # Expo configuration
├── package.json           # Dependencies
├── src/
│   ├── screens/          # Screen components
│   │   ├── RegisterScreen.tsx
│   │   ├── LoginScreen.tsx
│   │   ├── HomeScreen.tsx
│   │   └── ProfileScreen.tsx
│   ├── components/       # Reusable components
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   └── InterestTag.tsx
│   ├── services/         # API services
│   │   └── api.ts
│   ├── types/           # TypeScript types
│   │   └── user.ts
│   └── utils/           # Utility functions
│       └── storage.ts
```

## Step 3: Configuration

Update `app.json` to include your app details:

```json
{
  "expo": {
    "name": "Geotada",
    "slug": "geotada",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/icon.png",
    "splash": {
      "image": "./assets/splash.png",
      "resizeMode": "contain",
      "backgroundColor": "#667eea"
    },
    "ios": {
      "supportsTablet": true,
      "bundleIdentifier": "com.geotada.app"
    },
    "android": {
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#667eea"
      },
      "package": "com.geotada.app"
    }
  }
}
```

## Step 4: Create API Service

Create `src/services/api.ts`:

```typescript
import axios from 'axios';

// Change this to your computer's IP address when testing on a physical device
// Find your IP: ifconfig | grep "inet " | grep -v 127.0.0.1
const API_URL = 'http://localhost:8000';

export interface UserRegistration {
  email: string;
  username: string;
  password: string;
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  interests?: {
    categories: string[];
    preferences: {
      audio_enabled: boolean;
    };
  };
}

export interface UserLogin {
  email: string;
  password: string;
}

export const api = {
  async register(data: UserRegistration) {
    const response = await axios.post(`${API_URL}/users/register`, data);
    return response.data;
  },

  async login(data: UserLogin) {
    const response = await axios.post(`${API_URL}/users/login`, data);
    return response.data;
  },

  async getUser(userId: number, token: string) {
    const response = await axios.get(`${API_URL}/users/${userId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  },

  async updateUser(userId: number, data: Partial<UserRegistration>, token: string) {
    const response = await axios.put(`${API_URL}/users/${userId}`, data, {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  }
};
```

## Step 5: Start Development

```bash
# Make sure backend is running
cd /Users/adamserblowski/Geotada/backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In a new terminal, start mobile app
cd /Users/adamserblowski/Geotada/mobile
npm start
```

This will:
1. Start the Metro bundler
2. Show a QR code
3. Give you options to:
   - Press `w` to open in web browser
   - Press `i` to open iOS simulator (requires Xcode)
   - Press `a` to open Android emulator (requires Android Studio)
   - Scan QR code with Expo Go app on your phone

## Step 6: Install Expo Go App

To test on your physical device:

**iOS:**
1. Download "Expo Go" from the App Store
2. Open the app
3. Scan the QR code shown in your terminal

**Android:**
1. Download "Expo Go" from Google Play Store
2. Open the app
3. Scan the QR code shown in your terminal

## Step 7: Testing on Physical Device

If testing on a physical device, you need to:

1. Find your computer's local IP address:
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   ```

2. Update `API_URL` in `src/services/api.ts`:
   ```typescript
   const API_URL = 'http://192.168.x.x:8000';  // Your computer's IP
   ```

3. Make sure your phone and computer are on the same WiFi network

## Step 8: Build for Production

When ready for production:

```bash
# Install EAS CLI
npm install -g eas-cli

# Login to Expo
eas login

# Configure build
eas build:configure

# Build for iOS
eas build --platform ios

# Build for Android
eas build --platform android
```

## Helpful Resources

- **Expo Docs**: https://docs.expo.dev/
- **React Native Docs**: https://reactnative.dev/
- **React Navigation**: https://reactnavigation.org/
- **FastAPI Docs**: https://fastapi.tiangolo.com/

## Common Issues

### Issue: "Cannot connect to backend"
**Solution**:
- Make sure backend is running on port 8000
- Use your computer's IP address, not localhost, when testing on phone
- Check firewall settings

### Issue: "Module not found"
**Solution**:
```bash
# Clear cache and reinstall
rm -rf node_modules
npm install
npm start --clear
```

### Issue: "Expo Go app not connecting"
**Solution**:
- Ensure phone and computer are on same WiFi
- Try manually entering the URL in Expo Go
- Check if backend allows CORS from mobile

## Current Status

✅ **Completed:**
- Backend API with user authentication
- Database schema and migrations
- Comprehensive tests (24/24 passing)
- HTML demo frontend
- API documentation

⏳ **To Do:**
- Install Node.js
- Create React Native mobile app
- Implement registration screen
- Implement login screen
- Implement profile screen
- Add navigation between screens
- Connect to backend API
- Test on physical device
- Add points of interest features
- Integrate AI services

## Questions?

If you encounter any issues or have questions:
1. Check the [README.md](README.md) for detailed documentation
2. Review [DEMO_RESULTS.md](DEMO_RESULTS.md) for what's been accomplished
3. Check Expo documentation for mobile-specific issues
4. Review FastAPI documentation for backend issues

## Ready to Start?

Once Node.js is installed, run:

```bash
cd /Users/adamserblowski/Geotada
npx create-expo-app mobile --template blank-typescript
cd mobile
npm install axios @react-navigation/native @react-navigation/stack react-native-screens react-native-safe-area-context
npm start
```

Then I can help you build the registration and login screens!
