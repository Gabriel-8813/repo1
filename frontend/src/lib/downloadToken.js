import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export async function getDownloadToken() {
  const token = localStorage.getItem('meditrans_token');
  const r = await axios.get(`${API}/auth/download-token`, { headers: { Authorization: `Bearer ${token}` } });
  return r.data.token;
}

export async function openSecureUrl(url) {
  // Open synchronously so popup blockers see the user gesture, then point it at the signed URL
  const win = window.open('', '_blank');
  try {
    const t = await getDownloadToken();
    const signed = `${url}${url.includes('?') ? '&' : '?'}auth=${t}`;
    if (win) win.location = signed;
    else window.open(signed, '_blank');
  } catch (e) {
    if (win) win.close();
    throw e;
  }
}
