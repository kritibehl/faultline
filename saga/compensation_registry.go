package saga

var CompensationRegistry = map[string]string{
	"charge_payment":     "refund_payment",
	"reserve_inventory": "release_inventory",
	"create_shipping":   "cancel_shipping",
}
