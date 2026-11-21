import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export async function getDownloadToken() {
  const token = localStorage.getItem('meditrans_token');
  const r = await axios.get(`${API}/auth/download-token`, { headers: { Authorization: `Bearer ${token}` } });
  return r.data.token;
}

export async function openSecureUrl(url) {
  const t = await getDownloadToken();
  window.open(`${url}${url.includes('?') ? '&' : '?'}auth=${t}`, '_blank');
}
