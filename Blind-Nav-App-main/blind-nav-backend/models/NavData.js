const mongoose = require('mongoose');

const NavDataSchema = new mongoose.Schema({
  pairCode: { type: String, required: true, unique: true },
  emergencyContacts: [{ name: String, number: String }],
  friends: [{ name: String, number: String }],
  gps: {
    lat: { type: Number, default: 0 },
    lng: { type: Number, default: 0 },
    lastUpdated: { type: Date, default: Date.now }
  }
});

module.exports = mongoose.model('NavData', NavDataSchema);