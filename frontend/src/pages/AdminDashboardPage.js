import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import { Button } from '../components/ui/button';
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
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger
} from '../components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
  AlertDialogTrigger
} from '../components/ui/alert-dialog';
import {
  Shield, Truck, Users, Briefcase, DollarSign, Settings, LogOut,
  Trash2, Pencil, TrendingUp, CheckCircle, AlertCircle, Crown
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const AdminDashboardPage = () => {
  const navigate = useNavigate();
  const { user, token, logout } = useAuth();
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [plans, setPlans] = useState({});
  const [fees, setFees] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);

  const [editUser, setEditUser] = useState(null);
  const [editJob, setEditJob] = useState(null);
  const [editPlanId, setEditPlanId] = useState(null);
  const [planDraft, setPlanDraft] = useState({ name: '', price: '', features: '' });
  const [feeDraft, setFeeDraft] = useState(null);

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
      const [s, u, j, p, f, t] = await Promise.all([
        axios.get(`${API}/admin/stats`, { headers }),
        axios.get(`${API}/admin/users`, { headers }),
        axios.get(`${API}/admin/jobs`, { headers }),
        axios.get(`${API}/admin/plans`, { headers }),
        axios.get(`${API}/admin/fees`, { headers }),
        axios.get(`${API}/admin/transactions`, { headers }),
      ]);
      setStats(s.data);
      setUsers(u.data.users);
      setJobs(j.data.jobs);
      setPlans(p.data.plans);
      setFees(f.data.agreement);
      setFeeDraft(f.data.agreement);
      setTransactions(t.data.transactions);
    } catch (e) {
      toast.error('Failed to load admin data');
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => { logout(); navigate('/'); };

  // Users
  const saveUser = async () => {
    try {
      await axios.put(`${API}/admin/users/${editUser.id}`, {
        full_name: editUser.full_name,
        phone: editUser.phone,
        role: editUser.role,
        subscription_status: editUser.subscription_status || null,
        subscription_plan: editUser.subscription_plan || null,
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

  // Jobs
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

  // Plans
  const openPlanEditor = (id) => {
    const p = plans[id];
    setEditPlanId(id);
    setPlanDraft({
      name: p.name,
      price: p.price,
      features: (p.features || []).join('\n')
    });
  };
  const savePlan = async () => {
    try {
      await axios.put(`${API}/admin/plans/${editPlanId}`, {
        name: planDraft.name,
        price: Number(planDraft.price),
        features: planDraft.features.split('\n').map(s => s.trim()).filter(Boolean),
      }, { headers });
      toast.success('Plan updated');
      setEditPlanId(null);
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };

  // Fees
  const saveFees = async () => {
    try {
      await axios.put(`${API}/admin/fees`, {
        base_rate_per_km: Number(feeDraft.base_rate_per_km),
        minimum_fee: Number(feeDraft.minimum_fee),
        urgent_multiplier: Number(feeDraft.urgent_multiplier),
        emergency_multiplier: Number(feeDraft.emergency_multiplier),
        temperature_controlled_fee: Number(feeDraft.temperature_controlled_fee),
        platform_commission: Number(feeDraft.platform_commission),
      }, { headers });
      toast.success('Fee agreement updated');
      fetchAll();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
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
      {/* Navigation */}
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
            <p className="text-slate-600 mt-1">Manage users, jobs, plans and platform fees</p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid md:grid-cols-4 gap-6 mb-8">
          <StatCard icon={<Users className="w-6 h-6 text-blue-600" />} label="Total Users" value={stats.total_users} tone="blue" />
          <StatCard icon={<CheckCircle className="w-6 h-6 text-emerald-600" />} label="Active Subscriptions" value={stats.active_subscriptions} tone="emerald" />
          <StatCard icon={<Briefcase className="w-6 h-6 text-amber-600" />} label="Total Jobs" value={stats.total_jobs} subtitle={`${stats.open_jobs} open · ${stats.in_progress_jobs} in progress`} tone="amber" />
          <StatCard icon={<TrendingUp className="w-6 h-6 text-purple-600" />} label="Revenue (paid)" value={`$${stats.total_revenue.toFixed(2)}`} subtitle={`${stats.paid_transactions} transactions`} tone="purple" />
        </div>

        <Tabs defaultValue="users" className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="users" data-testid="tab-users"><Users className="w-4 h-4 mr-2" />Users</TabsTrigger>
            <TabsTrigger value="jobs" data-testid="tab-jobs"><Briefcase className="w-4 h-4 mr-2" />Jobs</TabsTrigger>
            <TabsTrigger value="plans" data-testid="tab-plans"><DollarSign className="w-4 h-4 mr-2" />Plans</TabsTrigger>
            <TabsTrigger value="fees" data-testid="tab-fees"><Settings className="w-4 h-4 mr-2" />Fees</TabsTrigger>
            <TabsTrigger value="tx" data-testid="tab-tx"><TrendingUp className="w-4 h-4 mr-2" />Transactions</TabsTrigger>
          </TabsList>

          {/* USERS */}
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
                      <TableHead>Subscription</TableHead>
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
                        <TableCell>
                          {u.subscription_plan ? (
                            <Badge className="bg-emerald-100 text-emerald-700 capitalize">{u.subscription_plan}</Badge>
                          ) : <span className="text-slate-400 text-xs">none</span>}
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
                                  This will permanently remove {u.email}. This cannot be undone.
                                </AlertDialogDescription>
                              </AlertDialogHeader>
                              <AlertDialogFooter>
                                <AlertDialogCancel>Cancel</AlertDialogCancel>
                                <AlertDialogAction onClick={() => deleteUser(u.id)} data-testid={`confirm-delete-user-${u.id}-btn`}>
                                  Delete
                                </AlertDialogAction>
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

          {/* JOBS */}
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
                            j.status === 'in_progress' ? 'bg-amber-100 text-amber-700' :
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
                                <AlertDialogAction onClick={() => deleteJob(j.id)} data-testid={`confirm-delete-job-${j.id}-btn`}>
                                  Delete
                                </AlertDialogAction>
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

          {/* PLANS */}
          <TabsContent value="plans">
            <div className="grid md:grid-cols-3 gap-6">
              {Object.entries(plans).map(([id, p]) => (
                <Card key={id} className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid={`plan-card-${id}`}>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="font-archivo capitalize">{p.name}</CardTitle>
                        <p className="text-3xl font-black mt-2">${p.price}<span className="text-sm text-slate-500 font-normal">/mo CAD</span></p>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => openPlanEditor(id)} data-testid={`edit-plan-${id}-btn`}>
                        <Pencil className="w-3 h-3 mr-1" /> Edit
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {(p.features || []).map((f, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <CheckCircle className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* FEES */}
          <TabsContent value="fees">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)] max-w-2xl">
              <CardHeader>
                <CardTitle className="font-archivo">Platform Fee Agreement</CardTitle>
                <p className="text-sm text-slate-500">Changes apply platform-wide immediately.</p>
              </CardHeader>
              <CardContent className="space-y-4">
                {feeDraft && (
                  <>
                    <FeeField label="Base Rate per KM (CAD)" value={feeDraft.base_rate_per_km}
                      onChange={v => setFeeDraft({ ...feeDraft, base_rate_per_km: v })} testid="fee-base-rate" />
                    <FeeField label="Minimum Fee (CAD)" value={feeDraft.minimum_fee}
                      onChange={v => setFeeDraft({ ...feeDraft, minimum_fee: v })} testid="fee-min" />
                    <FeeField label="Urgent Multiplier" value={feeDraft.urgent_multiplier}
                      onChange={v => setFeeDraft({ ...feeDraft, urgent_multiplier: v })} testid="fee-urgent" />
                    <FeeField label="Emergency Multiplier" value={feeDraft.emergency_multiplier}
                      onChange={v => setFeeDraft({ ...feeDraft, emergency_multiplier: v })} testid="fee-emergency" />
                    <FeeField label="Temperature Controlled Fee (CAD)" value={feeDraft.temperature_controlled_fee}
                      onChange={v => setFeeDraft({ ...feeDraft, temperature_controlled_fee: v })} testid="fee-temp" />
                    <FeeField label="Platform Commission (0-1)" value={feeDraft.platform_commission}
                      onChange={v => setFeeDraft({ ...feeDraft, platform_commission: v })} testid="fee-commission" />
                    <Button onClick={saveFees} className="bg-blue-600 hover:bg-blue-700 mt-2" data-testid="save-fees-btn">
                      Save Fee Agreement
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* TRANSACTIONS */}
          <TabsContent value="tx">
            <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
              <CardHeader><CardTitle className="font-archivo">Payment Transactions ({transactions.length})</CardTitle></CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Session</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>Plan</TableHead>
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
                        <TableCell className="capitalize">{tx.plan_id}</TableCell>
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
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
          </DialogHeader>
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
                <select
                  className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editUser.role}
                  onChange={e => setEditUser({ ...editUser, role: e.target.value })}
                  data-testid="edit-user-role-select"
                >
                  <option value="driver">driver</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <div><Label>Subscription Plan</Label>
                <select
                  className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editUser.subscription_plan || ''}
                  onChange={e => setEditUser({ ...editUser, subscription_plan: e.target.value })}
                >
                  <option value="">none</option>
                  {Object.keys(plans).map(id => <option key={id} value={id}>{id}</option>)}
                </select>
              </div>
              <div><Label>Subscription Status</Label>
                <select
                  className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editUser.subscription_status || ''}
                  onChange={e => setEditUser({ ...editUser, subscription_status: e.target.value })}
                >
                  <option value="">none</option>
                  <option value="active">active</option>
                  <option value="cancelled">cancelled</option>
                  <option value="expired">expired</option>
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
                <select
                  className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editJob.status}
                  onChange={e => setEditJob({ ...editJob, status: e.target.value })}
                  data-testid="edit-job-status-select"
                >
                  <option value="open">open</option>
                  <option value="in_progress">in_progress</option>
                  <option value="completed">completed</option>
                  <option value="cancelled">cancelled</option>
                </select>
              </div>
              <div><Label>Urgency</Label>
                <select
                  className="w-full h-10 rounded-md border border-slate-200 px-3"
                  value={editJob.urgency}
                  onChange={e => setEditJob({ ...editJob, urgency: e.target.value })}
                >
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

      {/* Edit Plan Dialog */}
      <Dialog open={!!editPlanId} onOpenChange={(o) => !o && setEditPlanId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Plan: {editPlanId}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Name</Label>
              <Input value={planDraft.name} onChange={e => setPlanDraft({ ...planDraft, name: e.target.value })} data-testid="edit-plan-name-input" />
            </div>
            <div><Label>Price (CAD)</Label>
              <Input type="number" value={planDraft.price} onChange={e => setPlanDraft({ ...planDraft, price: e.target.value })} data-testid="edit-plan-price-input" />
            </div>
            <div><Label>Features (one per line)</Label>
              <Textarea rows={5} value={planDraft.features} onChange={e => setPlanDraft({ ...planDraft, features: e.target.value })} data-testid="edit-plan-features-input" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditPlanId(null)}>Cancel</Button>
            <Button onClick={savePlan} className="bg-blue-600 hover:bg-blue-700" data-testid="save-plan-btn">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

const StatCard = ({ icon, label, value, subtitle, tone }) => {
  const toneMap = {
    blue: 'bg-blue-100', emerald: 'bg-emerald-100', amber: 'bg-amber-100', purple: 'bg-purple-100'
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

const FeeField = ({ label, value, onChange, testid }) => (
  <div>
    <Label>{label}</Label>
    <Input type="number" step="0.01" value={value} onChange={e => onChange(e.target.value)} data-testid={testid} />
  </div>
);

export default AdminDashboardPage;
