const mongoose = require('mongoose');

const UserSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true },
  password: { type: String, required: true },
  role: { type: String, enum: ['blind', 'advisor'], required: true },
  pairCode: { type: String, required: true } // Change 'groupId' to 'pairCode' here
});

module.exports = mongoose.model('User', UserSchema);