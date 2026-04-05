import React, { useEffect, useState, useCallback } from 'react';
import { 
  View, Text, StyleSheet, TouchableOpacity, FlatList, Modal, 
  TextInput, Alert, ScrollView, SafeAreaView, StatusBar, Dimensions, Platform, Image 
} from 'react-native';
import MapView, { Marker } from 'react-native-maps';
import { WebView } from 'react-native-webview'; 
import * as Haptics from 'expo-haptics';
import * as Location from 'expo-location';
import { cloudClient, piClient } from '../api/client';

const { width, height } = Dimensions.get('window');

export default function HomeScreen({ route, navigation }) {
  const { pairCode } = route.params;
  
  // --- STATE MANAGEMENT ---
  const [showStream, setShowStream] = useState(false);
  const [cloudData, setCloudData] = useState({ emergencyContacts: [], friends: [] });
  const [gallery, setGallery] = useState([]);
  const [loadingGallery, setLoadingGallery] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null); // For Full-Screen Preview
  const [navData, setNavData] = useState({ 
    gps: { lat: 21.2514, lng: 81.6296 }, 
    next_instruction: "Initializing..." 
  });
  
  const STREAM_URL = `http://pi.local:8002/video_feed`;

  const [destination, setDestination] = useState('');
  const [modalVisible, setModalVisible] = useState(false);
  const [addType, setAddType] = useState('emergency');
  const [newName, setNewName] = useState('');
  const [newNum, setNewNum] = useState('');

  // 1. CLOUD FETCH (MongoDB)
  const fetchCloudData = useCallback(async () => {
    try {
      const response = await cloudClient.get(`/data/${pairCode}`);
      setCloudData(response.data || { emergencyContacts: [], friends: [] });
    } catch (e) { console.log("Fetch Error:", e.message); }
  }, [pairCode]);

  // 2. GALLERY FETCH (Cloudinary Snaps)
  const fetchGallery = useCallback(async () => {
    setLoadingGallery(true);
    try {
      const response = await cloudClient.get(`/data/gallery/${pairCode}`);
      setGallery(response.data.images || []);
    } catch (e) { console.log("Gallery Error:", e.message); }
    finally { setLoadingGallery(false); }
  }, [pairCode]);

  const handleAddContact = async () => {
    if (!newName || !newNum) return Alert.alert("Error", "Please fill all fields");
    
    // Select endpoint based on addType state set by the buttons
    const endpoint = addType === 'emergency' ? '/data/add-emergency' : '/data/add-friend';
    
    try {
      await cloudClient.post(endpoint, { 
        pairCode: pairCode, 
        name: newName, 
        number: newNum 
      });
      
      setModalVisible(false);
      setNewName(''); 
      setNewNum('');
      
      if (Platform.OS !== 'web') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      
      // Refresh the lists immediately
      fetchAllData(); 
    } catch (e) {
      Alert.alert("Error", "Failed to save contact to MongoDB.");
    }
  };

  // 3. PI SYNC
  const syncWithPi = useCallback(async () => {
    try {
      let { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      let location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const { latitude, longitude } = location.coords;
      const response = await piClient.post('/update_and_get', { lat: latitude, lng: longitude });
      setNavData({ gps: { lat: latitude, lng: longitude }, next_instruction: response.data.instruction });
    } catch (e) { console.log("Pi Sync Error:", e.message); }
  }, []);

  useEffect(() => {
    fetchCloudData();
    fetchGallery();
    const interval = setInterval(syncWithPi, 3000);
    return () => clearInterval(interval);
  }, [fetchCloudData, fetchGallery, syncWithPi]);

  const renderContactItem = ({ item }) => (
    <View style={styles.listItem}>
      <View style={styles.itemInfo}>
        <View style={styles.avatar}><Text style={styles.avatarText}>{item.name?.charAt(0).toUpperCase()}</Text></View>
        <View>
          <Text style={styles.itemText}>{item.name}</Text>
          <Text style={styles.itemSub}>{item.number}</Text>
        </View>
      </View>
      <TouchableOpacity style={styles.callBtn}><Text style={styles.callText}>📞</Text></TouchableOpacity>
    </View>
  );

  const renderGalleryItem = ({ item }) => (
    <TouchableOpacity 
      style={styles.galleryCard} 
      onPress={() => {
        if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        setSelectedImage(item.url);
      }}
    >
      <Image source={{ uri: item.url }} style={styles.galleryImage} />
      <View style={styles.galleryTimeBadge}>
        <Text style={styles.galleryTimeText}>{item.timestamp}</Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />
      
      <SafeAreaView style={styles.header}>
        <View style={styles.headerContent}>
          <View>
            <Text style={styles.headerTitle}>DrishtiKon AI</Text>
            <View style={styles.badge}>
              <View style={styles.pulseDot} />
              <Text style={styles.headerSubtitle}>SYSTEM ACTIVE</Text>
            </View>
          </View>
          <TouchableOpacity onPress={() => navigation.replace('Auth')} style={styles.logoutBtn}>
            <Text style={styles.logoutText}>Logout</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 60 }}>
        
        {/* LIVE FEED TOGGLE */}
        <TouchableOpacity 
          style={[styles.streamToggleBtn, showStream && styles.streamToggleBtnActive]} 
          onPress={() => {
            if (Platform.OS !== 'web') Haptics.selectionAsync();
            setShowStream(!showStream);
          }}
        >
          <Text style={styles.btnText}>
            {showStream ? "▲ CLOSE VISION FEED" : "📷 OPEN VISION FEED"}
          </Text>
        </TouchableOpacity>

        {showStream && (
          <View style={styles.streamContainer}>
              <View style={styles.streamLabelRow}>
                  <Text style={styles.streamLabel}>LIVE NCNN STREAM</Text>
                  <View style={styles.recDot} />
              </View>
              <View style={styles.webViewWrapper}>
                  <WebView source={{ uri: STREAM_URL }} scrollEnabled={false} style={styles.videoStream} />
              </View>
          </View>
        )}

        <View style={styles.instructionCard}>
          <Text style={styles.instructionLabel}>SMART GUIDANCE</Text>
          <Text style={styles.instructionText}>{navData.next_instruction}</Text>
        </View>

        <View style={styles.mapContainer}>
          <MapView 
            style={styles.map} 
            userInterfaceStyle="dark" 
            region={{ latitude: navData.gps.lat, longitude: navData.gps.lng, latitudeDelta: 0.005, longitudeDelta: 0.005 }}
          >
            <Marker coordinate={{ latitude: navData.gps.lat, longitude: navData.gps.lng }}>
              <View style={styles.userMarker}><View style={styles.userMarkerInner} /></View>
            </Marker>
          </MapView>
        </View>

        <View style={styles.panel}>
          <View style={styles.searchRow}>
            <TextInput placeholder="Enter Destination..." style={styles.searchInput} placeholderTextColor="#888" onChangeText={setDestination} />
            <TouchableOpacity style={styles.goBtn} onPress={() => {}}>
              <Text style={styles.goText}>GO</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.buttonRow}>
          <TouchableOpacity 
            style={[styles.actionBtn, { backgroundColor: '#ff4444' }]} 
            onPress={() => { setAddType('emergency'); setModalVisible(true); }}
          >
            <Text style={styles.btnText}>+ EMERGENCY</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.actionBtn, { backgroundColor: '#007bff' }]} 
            onPress={() => { setAddType('friend'); setModalVisible(true); }}
          >
            <Text style={styles.btnText}>+ FRIEND</Text>
          </TouchableOpacity>
        </View>

          <Text style={styles.sectionTitle}>Emergency Network</Text>
          <FlatList 
            scrollEnabled={false}
            data={cloudData.emergencyContacts}
            renderItem={renderContactItem}
            keyExtractor={(item, index) => 'e-' + index}
            style={{ marginBottom: 20 }}
          />

          <Text style={styles.sectionTitle}>Friends</Text>
          <FlatList 
            scrollEnabled={false}
            data={cloudData.friends}
            renderItem={renderContactItem}
            keyExtractor={(item, index) => 'f-' + index}
            style={{ marginBottom: 30 }}
          />

          <Modal visible={modalVisible} animationType="fade" transparent={true}>
            {/* 1. This View covers the ENTIRE screen and dims it */}
            <View style={styles.modalOverlay}>
              
              {/* 2. This is the actual Box in the center */}
              <View style={styles.modalContent}>
                <Text style={styles.modalTitle}>Add {addType}</Text>
                
                <TextInput 
                  placeholder="Name" 
                  style={styles.modalInput} 
                  placeholderTextColor="#888" 
                  onChangeText={setNewName} 
                  value={newName}
                />
                
                <TextInput 
                  placeholder="Phone Number" 
                  style={styles.modalInput} 
                  placeholderTextColor="#888" 
                  keyboardType="phone-pad" 
                  onChangeText={setNewNum} 
                  value={newNum}
                />
                
                <View style={styles.modalButtons}>
                  <TouchableOpacity 
                    onPress={() => setModalVisible(false)} 
                    style={styles.cancelBtn}
                  >
                    <Text style={styles.btnText}>Cancel</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity 
                    onPress={handleAddContact} 
                    style={styles.saveBtn}
                  >
                    <Text style={styles.btnText}>Save</Text>
                  </TouchableOpacity>
                </View>
              </View>
              
            </View>
          </Modal>

          {/* --- RECENT SNAPS MOVED TO BOTTOM --- */}
          <View style={styles.gallerySection}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>Recent Snaps</Text>
              <TouchableOpacity onPress={fetchGallery}>
                <Text style={styles.refreshText}>{loadingGallery ? "..." : "↻ Sync"}</Text>
              </TouchableOpacity>
            </View>
            <FlatList 
              horizontal
              data={gallery}
              renderItem={renderGalleryItem}
              keyExtractor={(item) => item.id}
              showsHorizontalScrollIndicator={false}
              ListEmptyComponent={<Text style={styles.emptyText}>No cloud snaps found.</Text>}
              contentContainerStyle={styles.galleryList}
            />
          </View>
        </View>
      </ScrollView>

      {/* --- IMAGE PREVIEW MODAL --- */}
      <Modal visible={!!selectedImage} transparent={true} animationType="fade">
        <View style={styles.previewOverlay}>
          <TouchableOpacity 
            style={styles.closePreviewBtn} 
            onPress={() => setSelectedImage(null)}
          >
            <Text style={styles.closePreviewText}>✕</Text>
          </TouchableOpacity>
          <Image source={{ uri: selectedImage }} style={styles.fullImage} resizeMode="contain" />
        </View>
      </Modal>

      {/* CONTACT MODAL (Keeping existing) */}
      <Modal visible={modalVisible} animationType="slide" transparent={true}>
        {/* ... existing modal code ... */}
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  header: { backgroundColor: '#000', borderBottomWidth: 1, borderBottomColor: '#1A1A1A' },
  headerContent: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20 },
  headerTitle: { color: '#fff', fontSize: 24, fontWeight: '900', letterSpacing: -1 },
  badge: { flexDirection: 'row', alignItems: 'center', marginTop: 2 },
  pulseDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#28a745', marginRight: 6 },
  headerSubtitle: { color: '#28a745', fontSize: 10, fontWeight: '900' },
  logoutBtn: { padding: 8, borderRadius: 12, backgroundColor: '#1A1A1A' },
  logoutText: { color: '#666', fontWeight: 'bold', fontSize: 12 },

  // --- UPDATED GALLERY (BOTTOM) STYLES ---
  gallerySection: { marginTop: 10, paddingBottom: 20 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 },
  sectionTitle: { color: '#fff', fontSize: 18, fontWeight: '800' },
  refreshText: { color: '#007bff', fontSize: 12, fontWeight: 'bold' },
  galleryList: { paddingRight: 10 },
  galleryCard: { marginRight: 15, borderRadius: 18, overflow: 'hidden', backgroundColor: '#1A1A1A', borderWidth: 1, borderColor: '#333' },
  galleryImage: { width: 120, height: 160, resizeMode: 'cover' },
  galleryTimeBadge: { position: 'absolute', bottom: 8, left: 8, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  galleryTimeText: { color: '#fff', fontSize: 9, fontWeight: 'bold' },
  emptyText: { color: '#444', fontSize: 12, fontStyle: 'italic' },

  // --- IMAGE PREVIEW STYLES ---
  previewOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.95)', justifyContent: 'center', alignItems: 'center' },
  fullImage: { width: width, height: height * 0.8 },
  closePreviewBtn: { position: 'absolute', top: 50, right: 30, backgroundColor: '#333', width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center', zIndex: 10 },
  closePreviewText: { color: '#fff', fontSize: 20, fontWeight: 'bold' },

  streamToggleBtn: { backgroundColor: '#1A1A1A', margin: 20, padding: 18, borderRadius: 20, alignItems: 'center', borderWidth: 1, borderColor: '#333' },
  streamToggleBtnActive: { borderColor: '#ff4444' },
  btnText: { color: '#fff', fontWeight: '900', fontSize: 12 },

  streamContainer: { paddingHorizontal: 20, marginBottom: 20 },
  streamLabelRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  streamLabel: { color: '#ff4444', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  recDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#ff4444', marginLeft: 6 },
  webViewWrapper: { height: 250, borderRadius: 24, overflow: 'hidden', backgroundColor: '#000', borderWidth: 1, borderColor: '#333' },
  videoStream: { flex: 1 },

  instructionCard: { backgroundColor: '#007bff', marginHorizontal: 20, padding: 25, borderRadius: 24 },
  instructionLabel: { color: 'rgba(255,255,255,0.6)', fontSize: 10, fontWeight: '900' },
  instructionText: { color: '#fff', fontSize: 20, fontWeight: '800', marginTop: 4 },

  mapContainer: { height: 220, marginTop: 20, borderRadius: 24, overflow: 'hidden', marginHorizontal: 20 },
  map: { flex: 1 },
  userMarker: { width: 30, height: 30, borderRadius: 15, backgroundColor: 'rgba(0,123,255,0.2)', alignItems: 'center', justifyContent: 'center' },
  userMarkerInner: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#007bff', borderWidth: 2, borderColor: '#fff' },

  panel: { backgroundColor: '#0F0F0F', borderTopLeftRadius: 35, borderTopRightRadius: 35, padding: 25, marginTop: 20 },
  searchRow: { flexDirection: 'row', marginBottom: 25 },
  searchInput: { flex: 1, backgroundColor: '#1A1A1A', borderRadius: 18, padding: 18, color: '#fff', fontSize: 14 },
  goBtn: { backgroundColor: '#28a745', marginLeft: 12, paddingHorizontal: 25, borderRadius: 18, justifyContent: 'center' },
  goText: { color: '#fff', fontWeight: '900' },

  buttonRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 25 },
  actionBtn: { flex: 0.47, height: 55, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },

  listItem: { backgroundColor: '#1A1A1A', padding: 18, borderRadius: 20, marginBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  itemInfo: { flexDirection: 'row', alignItems: 'center' },
  avatar: { width: 45, height: 45, borderRadius: 14, backgroundColor: '#333', alignItems: 'center', justifyContent: 'center', marginRight: 15 },
  avatarText: { color: '#fff', fontWeight: 'bold', fontSize: 18 },
  itemText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  itemSub: { color: '#555', fontSize: 12, marginTop: 2 },
  callBtn: { backgroundColor: '#222', padding: 10, borderRadius: 12 },
  callText: { fontSize: 16 },
  modalOverlay: { 
    flex: 1, 
    backgroundColor: 'rgba(0,0,0,0.8)', // This creates the "dimmed" effect
    justifyContent: 'center',          // Center vertically
    alignItems: 'center',              // Center horizontally
  },
  modalContent: { 
    width: '85%',                      // Width of the popup
    backgroundColor: '#161616',        // Match your app's dark theme
    borderRadius: 25, 
    padding: 25, 
    borderWidth: 1, 
    borderColor: '#333',
    // Elevation/Shadow for depth
    elevation: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 15,
  },
  modalTitle: { 
    color: '#fff', 
    fontSize: 20, 
    fontWeight: '900', 
    marginBottom: 20, 
    textAlign: 'center',
    textTransform: 'capitalize' 
  },
  modalInput: { 
    backgroundColor: '#000', 
    borderRadius: 12, 
    padding: 15, 
    color: '#fff', 
    marginBottom: 15, 
    borderWidth: 1, 
    borderColor: '#222' 
  },
  modalButtons: { 
    flexDirection: 'row', 
    justifyContent: 'space-between',
    marginTop: 10
  },
  cancelBtn: { 
    flex: 0.48, 
    padding: 15, 
    borderRadius: 12, 
    backgroundColor: '#222', 
    alignItems: 'center' 
  },
  saveBtn: { 
    flex: 0.48, 
    padding: 15, 
    borderRadius: 12, 
    backgroundColor: '#28a745', 
    alignItems: 'center' 
  },
  btnText: { 
    color: '#fff', 
    fontWeight: 'bold',
    fontSize: 14 
  },
  
});