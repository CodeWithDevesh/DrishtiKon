import axios from 'axios';

// CLIENT 1: The MacBook (Cloud/Database)
// Used for: Login, Signup, Emergency Contacts, Friends List
export const cloudClient = axios.create({
  baseURL: 'http://Soumyajeets-MacBook-Air.local:8000/api' 
});

// CLIENT 2: The Raspberry Pi (The Brain)
// Used for: Sending iPhone GPS and getting live Navigation Instructions
export const piClient = axios.create({
  baseURL: 'http://pi.local:7000' 
});
