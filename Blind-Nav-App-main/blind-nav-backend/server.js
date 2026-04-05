const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const dotenv = require('dotenv');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const cloudinary = require('cloudinary').v2;

// Models
const User = require('./models/User');
const NavData = require('./models/NavData');

dotenv.config();
const app = express();

// --- MIDDLEWARE ---
app.use(express.json());
app.use(cors({ origin: '*', methods: ['GET', 'POST'], allowedHeaders: ['Content-Type', 'Authorization'] }));

// --- CLOUDINARY CONFIG ---
cloudinary.config({
  cloud_name: process.env.CLOUDINARY_CLOUD_NAME,
  api_key: process.env.CLOUDINARY_API_KEY,
  api_secret: process.env.CLOUDINARY_API_SECRET,
  secure: true
});

// --- DATABASE ---
mongoose.connect(process.env.MONGO_URI)
  .then(() => console.log("✅ MongoDB Connected"))
  .catch(err => console.error("❌ MongoDB Error:", err.message));

// --- AUTH ROUTES ---
app.post('/api/auth/register', async (req, res) => {
  const { email, password, pairCode } = req.body;
  try {
    const hashedPassword = await bcrypt.hash(password, 10);
    await User.create({ email, password: hashedPassword, pairCode });
    if (!await NavData.findOne({ pairCode })) {
      await NavData.create({ pairCode, emergencyContacts: [], friends: [], gps: { lat: 0, lng: 0 } });
    }
    res.status(201).json({ message: "Registered" });
  } catch (err) { res.status(400).json({ error: err.message }); }
});

app.post('/api/auth/login', async (req, res) => {
  const { email, password } = req.body;
  try {
    const user = await User.findOne({ email });
    if (user && await bcrypt.compare(password, user.password)) {
      const token = jwt.sign({ pairCode: user.pairCode }, process.env.JWT_SECRET);
      res.json({ token, pairCode: user.pairCode });
    } else res.status(401).json({ error: "Invalid credentials" });
  } catch (err) { res.status(500).json({ error: "Login failed" }); }
});

// --- DATA ROUTES ---

// 1. Get Snaps (Cloudinary)
app.get('/api/data/gallery/:pairCode', async (req, res) => {
  try {
    const result = await cloudinary.api.resources({
      type: 'upload',
      prefix: 'snap/',
      max_results: 15,
      direction: 'desc'
    });
    const images = result.resources.map(img => ({
      id: img.public_id,
      url: img.secure_url,
      timestamp: new Date(img.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }));
    res.json({ images });
  } catch (err) { res.status(500).json({ error: err.message }); }
});

// 2. Get Contacts & GPS
app.get('/api/data/:pairCode', async (req, res) => {
  const data = await NavData.findOne({ pairCode: req.params.pairCode });
  data ? res.json(data) : res.status(404).send();
});

// 3. Add Contacts
app.post('/api/data/add-emergency', async (req, res) => {
  const { pairCode, name, number } = req.body;
  await NavData.findOneAndUpdate({ pairCode }, { $push: { emergencyContacts: { name, number } } });
  res.json({ status: "Added" });
});

app.post('/api/data/add-friend', async (req, res) => {
  const { pairCode, name, number } = req.body;
  await NavData.findOneAndUpdate({ pairCode }, { $push: { friends: { name, number } } });
  res.json({ status: "Added" });
});

const PORT = process.env.PORT || 8000;
app.listen(PORT, () => console.log(`🚀 Server on port ${PORT}`));