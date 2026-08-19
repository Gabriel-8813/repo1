import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { NotificationBell } from '../components/NotificationBell';
import axios from 'axios';
import { Button } from '../components/ui/button';
import ChangePasswordDialog from '../components/ChangePasswordDialog';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '../components/ui/table';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle
} from '../components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger
} from '../components/ui/alert-dialog';
import {
  Shield, Truck, Users, Briefcase, DollarSign, Settings, LogOut,
  Trash2, Pencil, TrendingUp, AlertCircle, Crown, Percent, Receipt,
  FileText, Plus, Star, EyeOff, ShieldCheck
} from 'lucide-react';
import { toast } from 'sonner';
import { DriverVerificationTab } from '../components/DriverVerificationTab';
import { FacilityManagementTab } from '../components/FacilityManagementTab';
import { AdminRevenueTab } from '../components/AdminRevenueTab';
import { AdminComplianceTab } from '../components/AdminComplianceTab';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const AdminDashboardPage = () => {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [fees, setFees] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [permits, setPermits] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);

  const [editUser, setEditUser] = useState(null);
  const [editJob, setEditJob] = useState(null);
  const [feeDraft, setFeeDraft] = useState(null);
  const [editPermit, setEditPermit] = useState(null);
  const [newPermit, setNewPermit] = useState(null);

  const headers = { Authorization: `Bearer ${token}` };

  useEffect(() => {
    if (!user) return;
    if (user.role !== 'admin') {
      navigate('/dashboard');
      return;
    }
    fetchAll();
  }, [user, token]);

  const fetchAll = async () => {
    try {
      const [s, u, j, f, l, t, p, r] = await Promise.all([
        axios.get(`${API}/admin/stats`, { headers }),
        axios.get(`${API}/admin/users`, { headers }),
        axios.get(`${API}/admin/jobs`, { headers }),
        axios.get(`${API}/admin/fees`, { headers }),
        axios.get(`${API}/admin/ledger`, { headers }),
        axios.get(`${API}/admin/transactions`, { headers }),
        axios.get(`${API}/admin/permits`, { headers }),
        axios.get(`${API}/admin/reviews`, { headers }),
      ]);
      setStats(s.data);
      setUsers(u.data.users);
      setJobs(j.data.jobs);
      setFees(f.data.agreement);
      setFeeDraft(f.data.agreement);
      setLedger(l.data.entries);
      setTransactions(t.data.transactions);
      setPermits(p.data.permits);
      setReviews(r.data.reviews);
    } catch (e) {
      toast.error('Failed to load admin data');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => { logout(); navigate('/'); };

  const saveUser = async () => {
    try {
      await axios.put(`${API}/admin/users/${editUser.id}`, {
        full_name: editUser.full_name,
        phone: editUser.phone,
        role: editUser.role,
      }, { headers });
      toast.success('User updated');
      setEditUser(null);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };
  const deleteUser = async (id) => {
    try {
      await axios.delete(`${API}/admin/users/${id}`, { headers });
      toast.success('User deleted');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed');
    }
  };

  const saveJob = async () => {
    try {
      await axios.put(`${API}/admin/jobs/${editJob.id}`, {
        title: editJob.title,
        status: editJob.status,
        offered_price: Number(editJob.offered_price),
        urgency: editJob.urgency,
        notes: editJob.notes,
      }, { headers });
      toast.success('Job updated');
      setEditJob(null);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };
  const deleteJob = async (id) => {
    try {
      await axios.delete(`${API}/admin/jobs/${id}`, { headers });
      toast.success('Job deleted');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed');
    }
  };

  const saveFees = async () => {
    try {
      await axios.put(`${API}/admin/fees`, {
        base_rate_per_km: Number(feeDraft.base_rate_per_km),
        minimum_fee: Number(feeDraft.minimum_fee),
        urgent_multiplier: Number(feeDraft.urgent_multiplier),
        emergency_multiplier: Number(feeDraft.emergency_multiplier),
        temperature_controlled_fee: Number(feeDraft.temperature_controlled_fee),
        commission_rate: Number(feeDraft.commission_rate),
        cancellation_fee: Number(feeDraft.cancellation_fee),
        cancellation_grace_minutes: parseInt(feeDraft.cancellation_grace_minutes),
      }, { headers });
      toast.success('Fee agreement updated');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };

  const savePermit = async () => {
    try {
      await axios.put(`${API}/admin/permits/${editPermit.id}`, {
        name: editPermit.name,
        description: editPermit.description,
        issuing_authority: editPermit.issuing_authority,
        url: editPermit.url,
        required: editPermit.required,
      }, { headers });
      toast.success('Permit updated');
      setEditPermit(null);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };

  const createPermit = async () => {
    try {
      await axios.post(`${API}/admin/permits`, newPermit, { headers });
      toast.success('Permit created');
      setNewPermit(null);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Create failed');
    }
  };

  const deletePermit = async (id) => {
    try {
      await axios.delete(`${API}/admin/permits/${id}`, { headers });
      toast.success('Permit deleted');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed');
    }
  };

  const hideReview = async (id) => {
    try {
      await axios.post(`${API}/admin/reviews/${id}/hide`, {}, { headers });
      toast.success('Review hidden from public');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Hide failed');
    }
  };

  const deleteReview = async (id) => {
    try {
      await axios.delete(`${API}/admin/reviews/${id}`, { headers });
      toast.success('Review deleted');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Delete failed');
    }
  };

  if (loading || !stats) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="admin-dashboard-page">
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-2">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <Truck className="w-6 h-6 text-white" />
              </div>
              <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
            </Link>
            <div className="hidden md:flex items-center gap-1">
              <Link to="/dashboard" className="nav-link">Dashboard</Link>
              <Link to="/jobs" className="nav-link">Jobs</Link>
              <Link to="/permits" className="nav-link">Permits</Link>
              <Link to="/billing" className="nav-link">Billing</Link>
              <Link to="/admin" className="nav-link active">Admin</Link>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <Badge className="bg-purple-100 text-purple-700 gap-1" data-testid="admin-badge">
              <Crown className="w-3 h-3" /> Admin
            </Badge>
            <ChangePasswordDialog token={token} />
            <NotificationBell />
            <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="admin-logout-btn">
              <LogOut className="w-4 h-4 mr-2" /> Logout
            </Button>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-8 flex items-center gap-3">
          <Shield className="w-8 h-8 text-blue-600" />
          <div>
            <h1 className="font-archivo font-bold text-3xl text-slate-900">Admin Control Center</h1>
            <p className="text-slate-600 mt-1">Commission-based revenue · users, jobs, fees & ledger</p>
          </div>
        </div>

        <div className="grid md:grid-cols-4 gap-6 mb-8">
          <StatCard icon={<Users className="w-6 h-6 text-blue-600" />} label="Total Users" value={stats.total_users} tone="blue" />
          <StatCard icon={<Briefcase className="w-6 h-6 text-amber-600" />} label="Jobs" value={stats.total_jobs} subtitle={`${stats.open_jobs} open · ${stats.completed_jobs} completed`} tone="amber" />
          <StatCard icon={<TrendingUp className="w-6 h-6 text-emerald-600" />} label="Revenue (paid)" value={`$${stats.total_revenue.toFixed(2)}`} subtitle={`${stats.paid_transactions} transactions`} tone="emerald" />
          <StatCard icon={<AlertCircle className="w-6 h-6 text-red-600" />} label="Outstanding" value={`$${stats.total_outstanding.toFixed(2)}`} subtitle={`commission $${stats.commission_owed.toFixed(2)} · cancel $${stats.cancellation_fees_owed.toFixed(2)}`} tone="red" />
        </div>

        <Tabs defaultValue="users" className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="users" data-testid="tab-users"><Users className="w-4 h-4 mr-2" />Users</TabsTrigger>
            <TabsTrigger value="drivers" data-testid="tab-drivers"><ShieldCheck className="w-4 h-4 mr-2" />Drivers</TabsTrigger>
            <TabsTrigger value="facilities" data-testid="tab-facilities"><Truck className="w-4 h-4 mr-2" />Facilities</TabsTrigger>
            <TabsTrigger value="revenue" data-testid="tab-revenue"><TrendingUp className="w-4 h-4 mr-2" />Revenue</TabsTrigger>
            <TabsTrigger value="compliance" data-testid="tab-compliance"><ShieldCheck className="w-4 h-4 mr-2" />Compliance</TabsTrigger>
            <TabsTrigger value="jobs" data-testid="tab-jobs"><Briefcase className="w-4 h-4 mr-2" />Jobs</TabsTrigger>
            <TabsTrigger value="fees" data-testid="tab-fees"><Settings className="w-4 h-4 mr-2" />Fees & Commission</TabsTrigger>
            <TabsTrigger value="permits" data-testid="tab-permits"><FileText className="w-4 h-4 mr-2" />Permits</TabsTrigger>
            <TabsTrigger value="reviews" data-testid="tab-reviews"><Star className="w-4 h-4 mr-2" />Reviews</TabsTrigger>
            <TabsTrigger value="ledger" data-testid="tab-ledger"><Receipt className="w-4 h-4 mr-2" />Ledger</TabsTrigger>
            <TabsTrigger value="tx" data-testid="tab-tx"><DollarSign className="w-4 h-4 mr-2" />Transactions</TabsTrigger>
          </TabsList>

          <TabsContent value="users">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader><CardTitle className="font-archivo">All Users ({users.length})</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Email</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Role</TableHead>
                      <TableHead>Joined</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map(u => (
                      <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                        <TableCell className="font-medium">{u.email}</TableCell>
                        <TableCell>{u.full_name}</TableCell>
                        <TableCell>
                          <Badge className={u.role === 'admin' ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-700'}>
                            {u.role}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-slate-500 text-xs">
                          {new Date(u.created_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell className="text-right space-x-2">
                          <Button size="sm" variant="outline" onClick={() => setEditUser({ ...u })} data-testid={`edit-user-${u.id}-btn`}>
                            <Pencil className="w-3 h-3" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="outline" className="text-red-600" disabled={u.id === user.id} data-testid={`delete-user-${u.id}-btn`}>
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Delete user?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  This will permanently remove {u.email}.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => deleteUser(u.id)} data-testid={`confirm-delete-user-${u.id}-btn`}>Delete</AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="drivers">
            <DriverVerificationTab />
          </TabsContent>

          <TabsContent value="facilities">
            <FacilityManagementTab />
          </TabsContent>

          <TabsContent value="revenue">
            <AdminRevenueTab />
          </TabsContent>

          <TabsContent value="compliance">
            <AdminComplianceTab />
          </TabsContent>

          <TabsContent value="jobs">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader><CardTitle className="font-archivo">All Jobs ({jobs.length})</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Route</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Urgency</TableHead>
                      <TableHead>Price</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {jobs.length === 0 ? (
                      <TableRow><TableCell colSpan={6} className="text-center py-8 text-slate-400">No jobs yet</TableCell></TableRow>
                    ) : jobs.map(j => (
                      <TableRow key={j.id} data-testid={`job-row-${j.id}`}>
                        <TableCell className="font-medium">{j.title}</TableCell>
                        <TableCell className="text-xs text-slate-500">{j.pickup_city} → {j.delivery_city}</TableCell>
                        <TableCell>
                          <Badge className={
                            j.status === 'open' ? 'bg-blue-100 text-blue-700' :
                            j.status === 'in_progress' || j.status === 'accepted' ? 'bg-amber-100 text-amber-700' :
                            j.status === 'completed' ? 'bg-emerald-100 text-emerald-700' :
                            'bg-slate-100 text-slate-700'
                          }>{j.status}</Badge>
                        </TableCell>
                        <TableCell className="capitalize">{j.urgency}</TableCell>
                        <TableCell>${j.offered_price?.toFixed(2)}</TableCell>
                        <TableCell className="text-right space-x-2">
                          <Button size="sm" variant="outline" onClick={() => setEditJob({ ...j })} data-testid={`edit-job-${j.id}-btn`}>
                            <Pencil className="w-3 h-3" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="outline" className="text-red-600" data-testid={`delete-job-${j.id}-btn`}>
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Delete job?</AlertDialogTitle>
                                <AlertDialogDescription>This will permanently remove "{j.title}".</AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => deleteJob(j.id)} data-testid={`confirm-delete-job-${j.id}-btn`}>Delete</AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="fees">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] max-w-3xl">
              <CardHeader>
                <CardTitle className="font-archivo flex items-center gap-2">
                  <Percent className="w-5 h-5" /> Commission & Fee Agreement
                </CardTitle>
                <p className="text-sm text-slate-500">Platform-wide rates — changes apply immediately</p>
              </CardHeader>
              <CardContent className="space-y-4">
                {feeDraft && (
                  <div className="grid md:grid-cols-2 gap-4">
                    <FeeField label="Commission Rate (0-1)" hint="e.g. 0.20 = 20%"
                      value={feeDraft.commission_rate}
                      onChange={v => setFeeDraft({ ...feeDraft, commission_rate: v })} testid="fee-commission-rate" />
                    <FeeField label="Cancellation Fee (CAD)"
                      value={feeDraft.cancellation_fee}
                      onChange={v => setFeeDraft({ ...feeDraft, cancellation_fee: v })} testid="fee-cancellation" />
                    <FeeField label="Grace Window (minutes)"
                      value={feeDraft.cancellation_grace_minutes}
                      onChange={v => setFeeDraft({ ...feeDraft, cancellation_grace_minutes: v })} testid="fee-grace" step="1" />
                    <FeeField label="Base Rate per KM (CAD)"
                      value={feeDraft.base_rate_per_km}
                      onChange={v => setFeeDraft({ ...feeDraft, base_rate_per_km: v })} testid="fee-base-rate" />
                    <FeeField label="Minimum Trip Fee (CAD)"
                      value={feeDraft.minimum_fee}
                      onChange={v => setFeeDraft({ ...feeDraft, minimum_fee: v })} testid="fee-min" />
                    <FeeField label="Urgent Multiplier"
                      value={feeDraft.urgent_multiplier}
                      onChange={v => setFeeDraft({ ...feeDraft, urgent_multiplier: v })} testid="fee-urgent" />
                    <FeeField label="Emergency Multiplier"
                      value={feeDraft.emergency_multiplier}
                      onChange={v => setFeeDraft({ ...feeDraft, emergency_multiplier: v })} testid="fee-emergency" />
                    <FeeField label="Temp-Controlled Add-on (CAD)"
                      value={feeDraft.temperature_controlled_fee}
                      onChange={v => setFeeDraft({ ...feeDraft, temperature_controlled_fee: v })} testid="fee-temp" />
                  </div>
                )}
                <Button onClick={saveFees} className="bg-blue-600 hover:bg-blue-700" data-testid="save-fees-btn">
                  Save Changes
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="permits">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="font-archivo">Ontario Permit Requirements ({permits.length})</CardTitle>
                <Button
                  onClick={() => setNewPermit({ id: '', name: '', description: '', issuing_authority: '', url: '', required: true })}
                  className="bg-blue-600 hover:bg-blue-700"
                  data-testid="add-permit-btn"
                >
                  <Plus className="w-4 h-4 mr-2" /> Add Permit
                </Button>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Authority</TableHead>
                      <TableHead>Required</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {permits.length === 0 ? (
                      <TableRow><TableCell colSpan={5} className="text-center py-8 text-slate-400">No permits configured</TableCell></TableRow>
                    ) : permits.map(p => (
                      <TableRow key={p.id} data-testid={`permit-row-${p.id}`}>
                        <TableCell className="font-mono text-xs">{p.id}</TableCell>
                        <TableCell className="font-medium">{p.name}</TableCell>
                        <TableCell className="text-slate-600 text-sm">{p.issuing_authority}</TableCell>
                        <TableCell>
                          <Badge className={p.required ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-700'}>
                            {p.required ? 'Required' : 'Optional'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right space-x-2">
                          <Button size="sm" variant="outline" onClick={() => setEditPermit({ ...p })} data-testid={`edit-permit-${p.id}-btn`}>
                            <Pencil className="w-3 h-3" />
                          </Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="outline" className="text-red-600" data-testid={`delete-permit-${p.id}-btn`}>
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Delete permit?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  This removes "{p.name}" from the compliance checklist. Drivers will no longer see it.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => deletePermit(p.id)} data-testid={`confirm-delete-permit-${p.id}-btn`}>Delete</AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="reviews">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader><CardTitle className="font-archivo">Driver Reviews ({reviews.length})</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Rating</TableHead>
                      <TableHead>Reviewer</TableHead>
                      <TableHead>Comment</TableHead>
                      <TableHead>Driver</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reviews.length === 0 ? (
                      <TableRow><TableCell colSpan={7} className="text-center py-8 text-slate-400">No reviews yet</TableCell></TableRow>
                    ) : reviews.map(r => (
                      <TableRow key={r.id} data-testid={`review-row-${r.id}`}>
                        <TableCell>
                          <div className="flex items-center gap-0.5 text-amber-400">
                            {[...Array(r.rating)].map((_, i) => <Star key={i} className="w-3 h-3 fill-current" />)}
                            {[...Array(5 - r.rating)].map((_, i) => <Star key={'o'+i} className="w-3 h-3 text-slate-200 fill-current" />)}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm">{r.reviewer_name || <span className="text-slate-400">Anonymous</span>}</TableCell>
                        <TableCell className="max-w-xs">
                          <p className="text-sm text-slate-700 truncate">{r.comment || <span className="text-slate-400">—</span>}</p>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{r.driver_id?.slice(0, 8)}...</TableCell>
                        <TableCell>
                          <Badge className={r.hidden ? 'bg-slate-200 text-slate-600' : 'bg-emerald-100 text-emerald-700'}>
                            {r.hidden ? 'Hidden' : 'Public'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</TableCell>
                        <TableCell className="text-right space-x-2">
                          {!r.hidden && (
                            <Button size="sm" variant="outline" onClick={() => hideReview(r.id)} data-testid={`hide-review-${r.id}-btn`}>
                              <EyeOff className="w-3 h-3" />
                            </Button>
                          )}
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button size="sm" variant="outline" className="text-red-600" data-testid={`delete-review-${r.id}-btn`}>
                                <Trash2 className="w-3 h-3" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader>
                                <AlertDialogTitle>Delete review?</AlertDialogTitle>
                                <AlertDialogDescription>
                                  Permanently deletes this review. Consider hiding instead to preserve history.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => deleteReview(r.id)} data-testid={`confirm-delete-review-${r.id}-btn`}>Delete</AlertDialogAction>
                              </AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="ledger">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader><CardTitle className="font-archivo">Commission & Cancellation Ledger ({ledger.length})</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Driver</TableHead>
                      <TableHead>Job</TableHead>
                      <TableHead>Amount</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ledger.length === 0 ? (
                      <TableRow><TableCell colSpan={6} className="text-center py-8 text-slate-400">No ledger activity yet</TableCell></TableRow>
                    ) : ledger.map(e => (
                      <TableRow key={e.id}>
                        <TableCell>
                          <Badge className={e.type === 'commission' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'}>
                            {e.type === 'commission' ? 'Commission' : 'Cancellation'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{e.driver_id?.slice(0, 8)}...</TableCell>
                        <TableCell className="font-mono text-xs">{e.job_id?.slice(0, 8)}...</TableCell>
                        <TableCell className="font-semibold">${e.amount?.toFixed(2)}</TableCell>
                        <TableCell>
                          <Badge className={e.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}>
                            {e.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="tx">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader><CardTitle className="font-archivo">Payment Transactions ({transactions.length})</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Session</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Amount</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {transactions.length === 0 ? (
                      <TableRow><TableCell colSpan={6} className="text-center py-8 text-slate-400">No transactions yet</TableCell></TableRow>
                    ) : transactions.map(tx => (
                      <TableRow key={tx.id}>
                        <TableCell className="font-mono text-xs">{tx.session_id?.slice(0, 16)}...</TableCell>
                        <TableCell className="text-xs">{tx.user_id?.slice(0, 8)}...</TableCell>
                        <TableCell>{tx.payment_type || 'balance'}</TableCell>
                        <TableCell>${tx.amount?.toFixed(2)} {tx.currency?.toUpperCase()}</TableCell>
                        <TableCell>
                          <Badge className={tx.payment_status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}>
                            {tx.payment_status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-slate-500">{new Date(tx.created_at).toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      {/* Edit User Dialog */}
      <Dialog open={!!editUser} onOpenChange={(o) => !o && setEditUser(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit User</DialogTitle></DialogHeader>
          {editUser && (
            <div className="space-y-4">
              <div><Label>Email</Label><Input value={editUser.email} disabled /></div>
              <div><Label>Full Name</Label>
                <Input value={editUser.full_name || ''}
                  onChange={e => setEditUser({ ...editUser, full_name: e.target.value })}
                  data-testid="edit-user-name-input" />
              </div>
              <div><Label>Phone</Label>
                <Input value={editUser.phone || ''}
                  onChange={e => setEditUser({ ...editUser, phone: e.target.value })} />
              </div>
              <div><Label>Role</Label>
                <select className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editUser.role}
                  onChange={e => setEditUser({ ...editUser, role: e.target.value })}
                  data-testid="edit-user-role-select">
                  <option value="driver">driver</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditUser(null)}>Cancel</Button>
            <Button onClick={saveUser} className="bg-blue-600 hover:bg-blue-700" data-testid="save-user-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Job Dialog */}
      <Dialog open={!!editJob} onOpenChange={(o) => !o && setEditJob(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Job</DialogTitle></DialogHeader>
          {editJob && (
            <div className="space-y-4">
              <div><Label>Title</Label>
                <Input value={editJob.title || ''} onChange={e => setEditJob({ ...editJob, title: e.target.value })} data-testid="edit-job-title-input" />
              </div>
              <div><Label>Status</Label>
                <select className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editJob.status}
                  onChange={e => setEditJob({ ...editJob, status: e.target.value })}
                  data-testid="edit-job-status-select">
                  <option value="open">open</option>
                  <option value="offered">offered</option>
                  <option value="accepted">accepted</option>
                  <option value="in_progress">in_progress</option>
                  <option value="completed">completed</option>
                  <option value="cancelled">cancelled</option>
                </select>
              </div>
              <div><Label>Urgency</Label>
                <select className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editJob.urgency}
                  onChange={e => setEditJob({ ...editJob, urgency: e.target.value })}>
                  <option value="standard">standard</option>
                  <option value="urgent">urgent</option>
                  <option value="emergency">emergency</option>
                </select>
              </div>
              <div><Label>Offered Price (CAD)</Label>
                <Input type="number" value={editJob.offered_price} onChange={e => setEditJob({ ...editJob, offered_price: e.target.value })} />
              </div>
              <div><Label>Notes</Label>
                <Textarea value={editJob.notes || ''} onChange={e => setEditJob({ ...editJob, notes: e.target.value })} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditJob(null)}>Cancel</Button>
            <Button onClick={saveJob} className="bg-blue-600 hover:bg-blue-700" data-testid="save-job-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Edit Permit Dialog */}
      <Dialog open={!!editPermit} onOpenChange={(o) => !o && setEditPermit(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Edit Permit</DialogTitle></DialogHeader>
          {editPermit && (
            <div className="space-y-3">
              <div><Label>ID</Label><Input value={editPermit.id} disabled /></div>
              <div><Label>Name</Label>
                <Input value={editPermit.name}
                  onChange={e => setEditPermit({ ...editPermit, name: e.target.value })}
                  data-testid="edit-permit-name-input" />
              </div>
              <div><Label>Description</Label>
                <Textarea value={editPermit.description}
                  onChange={e => setEditPermit({ ...editPermit, description: e.target.value })} />
              </div>
              <div><Label>Issuing Authority</Label>
                <Input value={editPermit.issuing_authority}
                  onChange={e => setEditPermit({ ...editPermit, issuing_authority: e.target.value })} />
              </div>
              <div><Label>URL</Label>
                <Input value={editPermit.url}
                  onChange={e => setEditPermit({ ...editPermit, url: e.target.value })} />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="perm-required"
                  checked={!!editPermit.required}
                  onChange={e => setEditPermit({ ...editPermit, required: e.target.checked })}
                  data-testid="edit-permit-required-checkbox" />
                <Label htmlFor="perm-required" className="cursor-pointer">Required for drivers</Label>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditPermit(null)}>Cancel</Button>
            <Button onClick={savePermit} className="bg-blue-600 hover:bg-blue-700" data-testid="save-permit-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Permit Dialog */}
      <Dialog open={!!newPermit} onOpenChange={(o) => !o && setNewPermit(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Add Permit Requirement</DialogTitle></DialogHeader>
          {newPermit && (
            <div className="space-y-3">
              <div><Label>ID (lowercase, no spaces)</Label>
                <Input value={newPermit.id}
                  onChange={e => setNewPermit({ ...newPermit, id: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                  placeholder="e.g. hazmat_cert"
                  data-testid="new-permit-id-input" />
              </div>
              <div><Label>Name</Label>
                <Input value={newPermit.name}
                  onChange={e => setNewPermit({ ...newPermit, name: e.target.value })}
                  data-testid="new-permit-name-input" />
              </div>
              <div><Label>Description</Label>
                <Textarea value={newPermit.description}
                  onChange={e => setNewPermit({ ...newPermit, description: e.target.value })} />
              </div>
              <div><Label>Issuing Authority</Label>
                <Input value={newPermit.issuing_authority}
                  onChange={e => setNewPermit({ ...newPermit, issuing_authority: e.target.value })} />
              </div>
              <div><Label>URL</Label>
                <Input value={newPermit.url}
                  onChange={e => setNewPermit({ ...newPermit, url: e.target.value })}
                  placeholder="https://..." />
              </div>
              <div className="flex items-center gap-2">
                <input type="checkbox" id="new-perm-required"
                  checked={!!newPermit.required}
                  onChange={e => setNewPermit({ ...newPermit, required: e.target.checked })} />
                <Label htmlFor="new-perm-required" className="cursor-pointer">Required for drivers</Label>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setNewPermit(null)}>Cancel</Button>
            <Button onClick={createPermit}
              disabled={!newPermit?.id || !newPermit?.name}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="create-permit-btn">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const StatCard = ({ icon, label, value, subtitle, tone }) => {
  const toneMap = {
    blue: 'bg-blue-100', emerald: 'bg-emerald-100', amber: 'bg-amber-100',
    purple: 'bg-purple-100', red: 'bg-red-100'
  };
  return (
    <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
      <CardContent className="p-6">
        <div className={`w-12 h-12 ${toneMap[tone]} rounded-xl flex items-center justify-center mb-4`}>
          {icon}
        </div>
        <p className="text-sm text-slate-500 mb-1">{label}</p>
        <p className="font-archivo font-black text-3xl text-slate-900">{value}</p>
        {subtitle && <p className="text-xs text-slate-400 mt-1">{subtitle}</p>}
      </CardContent>
    </Card>
  );
};

const FeeField = ({ label, hint, value, onChange, testid, step = '0.01' }) => (
  <div>
    <Label>{label}</Label>
    <Input type="number" step={step} value={value} onChange={e => onChange(e.target.value)} data-testid={testid} />
    {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
  </div>
);

export default AdminDashboardPage;
