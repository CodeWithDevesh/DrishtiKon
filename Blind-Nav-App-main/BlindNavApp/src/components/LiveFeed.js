import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { WebView } from 'react-native-webview';

// Use your Pi's IP or .local address
const VIDEO_URL = "http://pi.local:9999/video_feed";

export default function LiveFeed() {
  const [showFeed, setShowFeed] = useState(false);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Live Environment Feed</Text>
      
      {showFeed ? (
        <View style={styles.videoContainer}>
          <WebView
            source={{ 
              uri: VIDEO_URL,
              headers: { 'ngrok-skip-browser-warning': 'true' } 
            }}
            style={styles.webview}
            scrollEnabled={false}
            onError={() => {
              setShowFeed(false);
              Alert.alert("Camera Offline", "Start camera_server.py on the Pi.");
            }}
          />
        </View>
      ) : (
        <View style={styles.placeholder}>
          <Text style={styles.placeholderText}>Camera Standby</Text>
        </View>
      )}

      <TouchableOpacity 
        style={[styles.btn, { backgroundColor: showFeed ? '#ff4444' : '#28a745' }]} 
        onPress={() => setShowFeed(!showFeed)}
      >
        <Text style={styles.btnText}>{showFeed ? "Stop Feed" : "Show Live Feed"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginHorizontal: 15, marginVertical: 10, padding: 15, backgroundColor: '#1c1c1e', borderRadius: 24, borderWidth: 1, borderColor: '#333' },
  title: { color: '#888', fontSize: 10, fontWeight: 'bold', letterSpacing: 1, marginBottom: 10, textTransform: 'uppercase' },
  videoContainer: { width: '100%', height: 220, borderRadius: 18, overflow: 'hidden', backgroundColor: '#000' },
  webview: { flex: 1, backgroundColor: '#000' },
  placeholder: { width: '100%', height: 220, backgroundColor: '#000', borderRadius: 18, justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: '#333', borderStyle: 'dashed' },
  placeholderText: { color: '#444', fontWeight: 'bold' },
  btn: { marginTop: 15, paddingVertical: 15, borderRadius: 16, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: 'bold' }
});