import React, { useState, useRef } from 'react';
import { 
  View, 
  Text, 
  TextInput, 
  TouchableOpacity, 
  StyleSheet, 
  Alert, 
  KeyboardAvoidingView, 
  Platform,
  ActivityIndicator,
  StatusBar,
  Animated,
  Pressable
} from 'react-native';
import { cloudClient } from '../api/client'; // Replace with your actual api client import

// Custom Emoji Component to ensure consistent icon rendering
const RoleIcon = ({ symbol }) => (
  <Text style={styles.roleIconSymbol} accessibilityElementsHidden={true}>{symbol}</Text>
);

export default function AuthScreen({ navigation }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pairCode, setPairCode] = useState('');
  const [role, setRole] = useState('blind');
  const [loading, setLoading] = useState(false);
  const [focusStates, setFocusStates] = useState({ email: false, password: false, pairCode: false });

  // 3D-like Animation Value for the Login Button
  const scaleLoginBtn = useRef(new Animated.Value(1)).current;

  const animateLoginPressIn = () => {
    Animated.spring(scaleLoginBtn, { toValue: 0.96, friction: 5, tension: 50, useNativeDriver: true }).start();
  };
  const animateLoginPressOut = () => {
    Animated.spring(scaleLoginBtn, { toValue: 1, friction: 3, tension: 60, useNativeDriver: true }).start();
  };

  const handleAuth = async (type) => {
    if (!email || !password) {
      Alert.alert("Input Required", "Please fill in your email and password.");
      return;
    }
    setLoading(true);
    try {
      const endpoint = type === 'login' ? '/auth/login' : '/auth/register';
      const response = await cloudClient.post(endpoint, { email, password, role, pairCode });
      
      // Navigate to Home screen and replace Auth from stack
      navigation.replace('Home', { pairCode: response.data.pairCode || pairCode, role: response.data.role || role });
    } catch (error) {
      Alert.alert("Authentication Failed", error.response?.data?.error || "Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#050505" />
      
      {/* Dynamic Background Decorators */}
      <View style={styles.blobTop} />
      <View style={styles.blobBottom} />

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.keyboardView}>
        <View style={styles.card}>
          <View style={styles.header}>
            <Text style={styles.title}>Drishtikon</Text>
            <Text style={styles.subtitle}>Empowering your perception</Text>
          </View>

          {/* Form Inputs with focus glowing effects */}
          <View style={styles.inputGroup}>
            <TextInput
              style={[styles.input, focusStates.email && styles.inputFocus]}
              placeholder="Email address"
              placeholderTextColor="#777"
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              onFocus={() => setFocusStates({...focusStates, email: true})}
              onBlur={() => setFocusStates({...focusStates, email: false})}
            />
            
            <TextInput
              style={[styles.input, focusStates.password && styles.inputFocus]}
              placeholder="Password"
              placeholderTextColor="#777"
              secureTextEntry
              onChangeText={setPassword}
              onFocus={() => setFocusStates({...focusStates, password: true})}
              onBlur={() => setFocusStates({...focusStates, password: false})}
            />
            
            <TextInput
              style={[styles.input, focusStates.pairCode && styles.inputFocus]}
              placeholder="Pair Code (Optional)"
              placeholderTextColor="#777"
              onChangeText={setPairCode}
              onFocus={() => setFocusStates({...focusStates, pairCode: true})}
              onBlur={() => setFocusStates({...focusStates, pairCode: false})}
            />
          </View>
          
          <Text style={styles.sectionLabel}>SELECT ROLE</Text>
          <View style={styles.roleContainer}>
            
            {/* Modern Pressable Role Button 1 (User) */}
            <Pressable 
              onPress={() => setRole('blind')}
              style={({ pressed }) => [
                styles.roleBtn, 
                role === 'blind' && styles.activeRole,
                pressed && { transform: [{ scale: 0.96 }], opacity: 0.9 }
              ]}
            >
              <View style={styles.roleContent}>
                <RoleIcon symbol="👤" />
                <Text style={[styles.roleText, role === 'blind' && styles.activeRoleText]}>User</Text>
              </View>
            </Pressable>

            <View style={styles.roleSeparator} />

            {/* Modern Pressable Role Button 2 (Guide) */}
            <Pressable 
              onPress={() => setRole('advisor')}
              style={({ pressed }) => [
                styles.roleBtn, 
                role === 'advisor' && styles.activeRole,
                pressed && { transform: [{ scale: 0.96 }], opacity: 0.9 }
              ]}
            >
              <View style={styles.roleContent}>
                <RoleIcon symbol="🧭" />
                <Text style={[styles.roleText, role === 'advisor' && styles.activeRoleText]}>Guide</Text>
              </View>
            </Pressable>

          </View>

          <View style={styles.actionContainer}>
            {/* Animated Login Button */}
            <Animated.View style={{ transform: [{ scale: scaleLoginBtn }] }}>
              <TouchableOpacity 
                style={[styles.primaryBtn, loading && styles.disabledBtn]} 
                onPress={() => handleAuth('login')}
                disabled={loading}
                activeOpacity={1}
                onPressIn={animateLoginPressIn}
                onPressOut={animateLoginPressOut}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.btnText}>Login</Text>
                )}
              </TouchableOpacity>
            </Animated.View>
            
            <TouchableOpacity 
              style={styles.secondaryBtn} 
              onPress={() => handleAuth('register')}
              disabled={loading}
            >
              <Text style={styles.secondaryBtnText}>Create new account</Text>
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: '#050505', 
  },
  keyboardView: {
    flex: 1,
    justifyContent: 'center', 
    padding: 20,
  },
  // Soft glowing background depth effects
  blobTop: {
    position: 'absolute',
    top: -120,
    right: -120,
    width: 320,
    height: 320,
    borderRadius: 160,
    backgroundColor: 'rgba(108, 99, 255, 0.16)', // Deep Purple/Blue halo
    transform: [{ scale: 1.6 }],
  },
  blobBottom: {
    position: 'absolute',
    bottom: -100,
    left: -60,
    width: 260,
    height: 260,
    borderRadius: 130,
    backgroundColor: 'rgba(0, 212, 255, 0.1)', // Subtle Teal depth
  },
  // Main Glassmorphism Card
  card: { 
    backgroundColor: 'rgba(25, 25, 28, 0.82)',
    padding: 30,
    borderRadius: 30,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.06)',
    // Complex 3D Shadow and elevation for depth
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 26 },
    shadowOpacity: 0.55,
    shadowRadius: 36,
    elevation: 20,
  },
  header: {
    alignItems: 'center',
    marginBottom: 40,
  },
  title: { 
    fontSize: 40, 
    fontWeight: '800', 
    color: '#ffffff', 
    letterSpacing: -1.6,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#999',
    fontWeight: '500',
    letterSpacing: 0.6,
  },
  inputGroup: {
    marginBottom: 20,
  },
  input: { 
    backgroundColor: '#121212',
    color: '#fff', 
    padding: 18, 
    borderRadius: 16, 
    marginBottom: 14,
    fontSize: 16,
    borderWidth: 1,
    borderColor: '#222',
  },
  inputFocus: {
    borderColor: '#6C63FF', // Primary Purple accent on focus
    backgroundColor: '#1a1a26', // Sightly lighter focused input
  },
  sectionLabel: {
    color: '#666',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.8,
    marginBottom: 12,
    marginLeft: 6,
  },
  roleContainer: { 
    flexDirection: 'row', 
    justifyContent: 'space-between', 
    marginBottom: 36,
  },
  roleBtn: { 
    flex: 1, 
    paddingVertical: 18, 
    borderRadius: 20,
    backgroundColor: '#121212',
    borderWidth: 1,
    borderColor: '#222',
  },
  activeRole: { 
    backgroundColor: 'rgba(108, 99, 255, 0.1)', // Soft glow for active button
    borderColor: '#6C63FF', // Stronger accent border
  },
  roleContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  roleIconSymbol: {
    fontSize: 22,
    marginRight: 8,
  },
  roleText: { 
    color: '#888', 
    fontWeight: '600',
    fontSize: 15,
  },
  activeRoleText: {
    color: '#6C63FF',
    fontWeight: '700',
  },
  roleSeparator: {
    width: 12,
  },
  actionContainer: {
    marginTop: 10,
  },
  primaryBtn: { 
    backgroundColor: '#6C63FF',
    paddingVertical: 18, 
    borderRadius: 16, 
    alignItems: 'center',
    marginBottom: 16,
    // Complex shadow/glow for the primary button
    shadowColor: '#6C63FF',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.4,
    shadowRadius: 18,
    elevation: 10,
  },
  disabledBtn: {
    backgroundColor: '#4a44b3',
    shadowOpacity: 0,
    elevation: 0,
  },
  btnText: { 
    color: '#fff', 
    fontWeight: '700', 
    fontSize: 16,
    letterSpacing: 0.6,
  },
  secondaryBtn: {
    paddingVertical: 14,
    alignItems: 'center',
  },
  secondaryBtnText: {
    color: '#aaa',
    fontWeight: '600',
    fontSize: 15,
  },
});